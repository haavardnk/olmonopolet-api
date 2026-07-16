import io
from unittest.mock import patch

import pytest
from beers.models import (
    Badge,
    Release,
    Stock,
    Tasted,
    UntappdRssFeed,
    UserList,
    UserListItem,
    WrongMatch,
)
from beers.tests.factories import (
    BeerFactory,
    CountryFactory,
    StockFactory,
    StoreFactory,
    UserFactory,
)
from beers.vmp import VmpApiError, VmpBlockedError
from django.core.cache import cache
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()


@pytest.fixture
def auth_client() -> tuple[APIClient, any]:
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestBeerViewSet:
    def test_stock_prefetch(self, auth_client: tuple) -> None:
        client, _user = auth_client
        beer = BeerFactory()
        store = StoreFactory(store_id=500)
        StockFactory(store=store, beer=beer, quantity=5)
        response = client.get(f"/beers/{beer.pk}/?store=500")
        assert response.data["stock"] == 5

    def test_badge_prefetch(self, auth_client: tuple) -> None:
        client, _user = auth_client
        beer = BeerFactory()
        Badge.objects.create(beer=beer, text="New", type="info")
        response = client.get(f"/beers/{beer.pk}/")
        assert response.data["badges"][0]["text"] == "New"

    def test_beers_param_filters(self, auth_client: tuple) -> None:
        client, _user = auth_client
        b1 = BeerFactory()
        b2 = BeerFactory()
        BeerFactory()
        response = client.get(f"/beers/?beers={b1.vmp_id},{b2.vmp_id}")
        ids = {r["vmp_id"] for r in response.data["results"]}
        assert ids == {b1.vmp_id, b2.vmp_id}

    def test_styles_action(self, auth_client: tuple) -> None:
        client, _user = auth_client
        BeerFactory(active=True, style="IPA")
        BeerFactory(active=True, style="Stout")
        BeerFactory(active=True, style="IPA")
        response = client.get("/beers/styles/")
        assert set(response.data) == {"IPA", "Stout"}


@pytest.mark.django_db
class TestBulkMarkTasted:
    @pytest.mark.parametrize(
        "file_data,file_name,error_fragment",
        [
            (None, None, "No file"),
            (b"some data", "data.txt", "Unsupported"),
            (b"checkin_id,bid,rating_score,created_at\n", "checkins.csv", "No valid"),
        ],
        ids=["no-file", "bad-format", "empty-csv"],
    )
    def test_invalid_upload_returns_400(
        self,
        auth_client: tuple,
        file_data: bytes | None,
        file_name: str | None,
        error_fragment: str,
    ) -> None:
        client, _user = auth_client
        if file_data is None:
            response = client.post("/beers/bulk_mark_tasted/")
        else:
            f = io.BytesIO(file_data)
            f.name = file_name
            response = client.post("/beers/bulk_mark_tasted/", {"file": f})
        assert response.status_code == 400
        assert error_fragment in response.data["error"]

    def test_csv_import_creates_tasted(self, auth_client: tuple) -> None:
        client, user = auth_client
        beer = BeerFactory(untpd_id=99999)
        csv_content = f"checkin_id,bid,rating_score,created_at\n1,{beer.untpd_id},4.0,2024-01-01 12:00:00\n"
        f = io.BytesIO(csv_content.encode())
        f.name = "checkins.csv"
        response = client.post("/beers/bulk_mark_tasted/", {"file": f})
        assert response.status_code == 200
        assert Tasted.objects.filter(user=user, beer=beer).exists()


@pytest.mark.django_db
class TestStockChangeViewSet:
    @pytest.mark.parametrize(
        "tasted,expected", [(True, True), (False, False)], ids=["tasted", "not-tasted"]
    )
    def test_user_tasted_annotation(
        self, auth_client: tuple, tasted: bool, expected: bool
    ) -> None:
        client, user = auth_client
        beer = BeerFactory()
        store = StoreFactory()
        StockFactory(store=store, beer=beer, quantity=5)
        Stock.objects.filter(beer=beer, store=store).update(stocked_at=timezone.now())
        if tasted:
            Tasted.objects.create(user=user, beer=beer)
        response = client.get("/stockchange/")
        results = response.data.get("results", response.data)
        matched = [r for r in results if r["beer"]["vmp_id"] == beer.vmp_id]
        assert matched[0]["beer"]["user_tasted"] is expected


@pytest.mark.django_db
class TestCountryViewSet:
    def test_active_countries(self, auth_client: tuple) -> None:
        client, _user = auth_client
        c1 = CountryFactory(name="Norway", iso_code="NO")
        c2 = CountryFactory(name="Sweden", iso_code="SE")
        CountryFactory(name="Finland", iso_code="FI")
        BeerFactory(country=c1, active=True)
        BeerFactory(country=c2, active=True)
        response = client.get("/countries/active/")
        names = {c["name"] for c in response.data}
        assert "Norway" in names
        assert "Sweden" in names
        assert "Finland" not in names


@pytest.mark.django_db
class TestReleaseViewSet:
    def test_release_list_is_cached(self) -> None:
        client = APIClient()
        release = Release.objects.create(name="Release Test")
        release.beer.add(BeerFactory(main_category="Øl"))

        first_response = client.get("/release/")
        assert first_response.data["results"][0]["beer_count"] == 1

        release.beer.add(BeerFactory(main_category="Øl"))

        cached_response = client.get("/release/")
        assert cached_response.data["results"][0]["beer_count"] == 1

        cache.clear()
        fresh_response = client.get("/release/")
        assert fresh_response.data["results"][0]["beer_count"] == 2


@pytest.mark.django_db
class TestUserListViewSet:
    def test_sort_order_auto_increments(self, auth_client: tuple) -> None:
        client, user = auth_client
        client.post("/lists/", {"name": "First"})
        client.post("/lists/", {"name": "Second"})
        first = UserList.objects.get(user=user, name="First")
        second = UserList.objects.get(user=user, name="Second")
        assert first.sort_order == 1
        assert second.sort_order == 2

    def test_add_item_success(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        response = client.post(
            f"/lists/{user_list.pk}/items/", {"product_id": str(beer.vmp_id)}
        )
        assert response.status_code == 201

    def test_add_item_duplicate_returns_409(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        UserListItem.objects.create(
            list=user_list, product_id=str(beer.vmp_id), sort_order=1
        )
        response = client.post(
            f"/lists/{user_list.pk}/items/", {"product_id": str(beer.vmp_id)}
        )
        assert response.status_code == 409

    def test_add_item_to_untappd_list_blocked(self, auth_client: tuple) -> None:
        client, user = auth_client
        from beers.models import UntappdList

        untappd_list = UntappdList.objects.create(
            untappd_list_id=1, untappd_username="test", name="Test"
        )
        user_list = UserList.objects.create(
            user=user, name="Untappd", sort_order=1, untappd_list=untappd_list
        )
        beer = BeerFactory()
        response = client.post(
            f"/lists/{user_list.pk}/items/", {"product_id": str(beer.vmp_id)}
        )
        assert response.status_code == 403

    def test_item_detail_patch(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        item = UserListItem.objects.create(
            list=user_list, product_id=str(beer.vmp_id), sort_order=1, quantity=1
        )
        response = client.patch(
            f"/lists/{user_list.pk}/items/{item.pk}/", {"quantity": 3}
        )
        assert response.status_code == 200
        item.refresh_from_db()
        assert item.quantity == 3

    def test_item_detail_delete(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        item = UserListItem.objects.create(
            list=user_list, product_id=str(beer.vmp_id), sort_order=1
        )
        response = client.delete(f"/lists/{user_list.pk}/items/{item.pk}/")
        assert response.status_code == 204
        assert not UserListItem.objects.filter(pk=item.pk).exists()

    def test_product_detail_delete(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        UserListItem.objects.create(
            list=user_list, product_id=str(beer.vmp_id), sort_order=1
        )
        response = client.delete(f"/lists/{user_list.pk}/products/{beer.vmp_id}/")
        assert response.status_code == 204
        assert not UserListItem.objects.filter(
            list=user_list, product_id=str(beer.vmp_id)
        ).exists()

    def test_shared_list_via_token(self) -> None:
        user = UserFactory()
        user_list = UserList.objects.create(user=user, name="Shared", sort_order=1)
        token = user_list.share_token
        client = APIClient()
        response = client.get(f"/lists/shared/{token}/")
        assert response.status_code == 200
        assert response.data["name"] == "Shared"

    def test_reorder_lists(self, auth_client: tuple) -> None:
        client, user = auth_client
        l1 = UserList.objects.create(user=user, name="A", sort_order=1)
        l2 = UserList.objects.create(user=user, name="B", sort_order=2)
        response = client.post(
            "/lists/reorder/", {"list_ids": [l2.pk, l1.pk]}, format="json"
        )
        assert response.status_code == 204
        l1.refresh_from_db()
        l2.refresh_from_db()
        assert l2.sort_order == 0
        assert l1.sort_order == 1

    def test_reorder_items(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        b1 = BeerFactory()
        b2 = BeerFactory()
        i1 = UserListItem.objects.create(
            list=user_list, product_id=str(b1.vmp_id), sort_order=1
        )
        i2 = UserListItem.objects.create(
            list=user_list, product_id=str(b2.vmp_id), sort_order=2
        )
        response = client.post(
            f"/lists/{user_list.pk}/items/reorder/",
            {"item_ids": [i2.pk, i1.pk]},
            format="json",
        )
        assert response.status_code == 204
        i1.refresh_from_db()
        i2.refresh_from_db()
        assert i2.sort_order == 0
        assert i1.sort_order == 1

    def test_destroy_cleans_up(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Delete Me", sort_order=1)
        beer = BeerFactory()
        UserListItem.objects.create(
            list=user_list, product_id=str(beer.vmp_id), sort_order=1
        )
        response = client.delete(f"/lists/{user_list.pk}/")
        assert response.status_code == 204
        assert not UserList.objects.filter(pk=user_list.pk).exists()

    def test_retrieve_includes_items(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        UserListItem.objects.create(
            list=user_list, product_id=str(beer.vmp_id), sort_order=1
        )
        response = client.get(f"/lists/{user_list.pk}/")
        assert response.status_code == 200
        assert len(response.data["items"]) == 1

    def test_list_excludes_items(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        UserListItem.objects.create(
            list=user_list, product_id=str(beer.vmp_id), sort_order=1
        )
        response = client.get("/lists/")
        assert "items" not in response.data[0]

    def test_create_with_flags(self, auth_client: tuple) -> None:
        client, _user = auth_client
        response = client.post(
            "/lists/",
            {
                "name": "Flagged",
                "show_quantity": True,
                "show_store": True,
                "show_vintage": False,
                "show_prices": True,
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["show_quantity"] is True
        assert response.data["show_store"] is True
        assert response.data["show_vintage"] is False
        assert response.data["show_prices"] is True

    def test_create_with_list_type_backward_compat(self, auth_client: tuple) -> None:
        client, _user = auth_client
        response = client.post(
            "/lists/",
            {"name": "Shopping BC", "list_type": "shopping"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["show_quantity"] is True
        assert response.data["show_store"] is True
        assert response.data["show_vintage"] is False

    def test_create_cellar_backward_compat(self, auth_client: tuple) -> None:
        client, _user = auth_client
        response = client.post(
            "/lists/",
            {"name": "Cellar BC", "list_type": "cellar"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["show_quantity"] is True
        assert response.data["show_vintage"] is True
        assert response.data["show_store"] is False

    def test_update_flags(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        response = client.patch(
            f"/lists/{user_list.pk}/",
            {"show_vintage": True, "show_quantity": True},
            format="json",
        )
        assert response.status_code == 200
        user_list.refresh_from_db()
        assert user_list.show_vintage is True
        assert user_list.show_quantity is True

    def test_flags_in_response(self, auth_client: tuple) -> None:
        client, user = auth_client
        UserList.objects.create(
            user=user,
            name="Full",
            sort_order=1,
            show_quantity=True,
            show_store=True,
        )
        response = client.get("/lists/")
        assert response.status_code == 200
        data = response.data[0]
        assert data["show_quantity"] is True
        assert data["show_store"] is True
        assert data["show_vintage"] is False
        assert data["show_prices"] is True

    def test_stats_only_when_show_vintage(self, auth_client: tuple) -> None:
        client, user = auth_client
        no_vintage = UserList.objects.create(
            user=user, name="No Vintage", sort_order=1, show_vintage=False
        )
        with_vintage = UserList.objects.create(
            user=user, name="With Vintage", sort_order=2, show_vintage=True
        )
        response_no = client.get(f"/lists/{no_vintage.pk}/")
        assert "stats" not in response_no.data
        response_yes = client.get(f"/lists/{with_vintage.pk}/")
        assert "stats" in response_yes.data

    def test_total_price_only_when_show_store(self, auth_client: tuple) -> None:
        client, user = auth_client
        no_store = UserList.objects.create(
            user=user, name="No Store", sort_order=1, show_store=False
        )
        with_store = UserList.objects.create(
            user=user, name="With Store", sort_order=2, show_store=True
        )
        response_no = client.get(f"/lists/{no_store.pk}/")
        assert "total_price" not in response_no.data
        response_yes = client.get(f"/lists/{with_store.pk}/")
        assert "total_price" in response_yes.data

    def test_shared_list_includes_flags(self) -> None:
        user = UserFactory()
        user_list = UserList.objects.create(
            user=user,
            name="Shared Flags",
            sort_order=1,
            show_quantity=True,
            show_store=True,
        )
        client = APIClient()
        response = client.get(f"/lists/shared/{user_list.share_token}/")
        assert response.status_code == 200
        assert response.data["show_quantity"] is True
        assert response.data["show_store"] is True


@pytest.mark.django_db
class TestWrongMatchViewSet:
    def test_create_unauthenticated(self) -> None:
        client = APIClient()
        beer = BeerFactory()
        response = client.post(
            "/wrongmatch/",
            {"beer": beer.pk, "suggested_url": "https://untappd.com/beer/22222"},
        )
        assert response.status_code == 201
        assert WrongMatch.objects.filter(beer=beer).exists()


@pytest.mark.django_db
class TestUntappdRssFeedMe:
    def test_get_no_feed_returns_404(self, auth_client: tuple) -> None:
        client, _user = auth_client
        response = client.get("/rss/me/")
        assert response.status_code == 404

    def test_put_creates_feed(self, auth_client: tuple) -> None:
        client, user = auth_client
        response = client.put(
            "/rss/me/",
            {"feed_url": "https://untappd.com/rss/user/newuser?key=xyz789"},
        )
        assert response.status_code == 201
        assert UntappdRssFeed.objects.filter(user=user).exists()

    def test_delete_existing_feed(self, auth_client: tuple) -> None:
        client, user = auth_client
        UntappdRssFeed.objects.create(
            user=user,
            feed_url="https://untappd.com/rss/user/testuser?key=abc123",
        )
        response = client.delete("/rss/me/")
        assert response.status_code == 204
        assert not UntappdRssFeed.objects.filter(user=user).exists()

    def test_unauthenticated_returns_401(self) -> None:
        client = APIClient()
        response = client.get("/rss/me/")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestSharedUserListSerializer:
    def test_pops_null_fields(self) -> None:
        user = UserFactory()
        user_list = UserList.objects.create(user=user, name="Shared", sort_order=1)
        client = APIClient()
        response = client.get(f"/lists/shared/{user_list.share_token}/")
        assert response.status_code == 200
        assert "is_past" not in response.data
        assert "stats" not in response.data
        assert "untappd_list_id" not in response.data

    def test_includes_user_name(self) -> None:
        user = UserFactory()
        user.first_name = "Test"
        user.last_name = "User"
        user.save()
        user_list = UserList.objects.create(user=user, name="Shared", sort_order=1)
        client = APIClient()
        response = client.get(f"/lists/shared/{user_list.share_token}/")
        assert response.data["user_name"] == "Test User"

    def test_includes_store_name(self) -> None:
        user = UserFactory()
        store = StoreFactory(store_id=999, name="My Store")
        user_list = UserList.objects.create(
            user=user, name="Shared", sort_order=1, selected_store_id=store.store_id
        )
        client = APIClient()
        response = client.get(f"/lists/shared/{user_list.share_token}/")
        assert response.data["store_name"] == "My Store"


@pytest.mark.django_db
class TestBarcodeLookup:
    def test_match_returns_beer(self) -> None:
        client = APIClient()
        beer = BeerFactory(vmp_id=3246802)
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            mock_factory.return_value.barcode_search.return_value = "3246802"
            response = client.get("/beers/barcode/?code=5410908000036")
        assert response.status_code == 200
        assert response.data["vmp_id"] == beer.vmp_id

    def test_vmp_no_match_returns_404(self) -> None:
        client = APIClient()
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            mock_factory.return_value.barcode_search.return_value = None
            response = client.get("/beers/barcode/?code=5410908000036")
        assert response.status_code == 404

    def test_vmp_match_but_no_local_beer_returns_404(self) -> None:
        client = APIClient()
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            mock_factory.return_value.barcode_search.return_value = "3246802"
            response = client.get("/beers/barcode/?code=5410908000036")
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "code", ["", "abc", "12x34"], ids=["empty", "alpha", "mixed"]
    )
    def test_invalid_code_returns_400(self, code: str) -> None:
        client = APIClient()
        response = client.get(f"/beers/barcode/?code={code}")
        assert response.status_code == 400

    def test_blocked_returns_503(self) -> None:
        client = APIClient()
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            mock_factory.return_value.barcode_search.side_effect = VmpBlockedError()
            response = client.get("/beers/barcode/?code=5410908000036")
        assert response.status_code == 503

    def test_api_error_returns_502(self) -> None:
        client = APIClient()
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            mock_factory.return_value.barcode_search.side_effect = VmpApiError()
            response = client.get("/beers/barcode/?code=5410908000036")
        assert response.status_code == 502

    def test_positive_result_is_cached(self) -> None:
        client = APIClient()
        BeerFactory(vmp_id=3246802)
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            search = mock_factory.return_value.barcode_search
            search.return_value = "3246802"
            client.get("/beers/barcode/?code=5410908000036")
            client.get("/beers/barcode/?code=5410908000036")
            assert search.call_count == 1

    def test_negative_result_is_cached(self) -> None:
        client = APIClient()
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            search = mock_factory.return_value.barcode_search
            search.return_value = None
            client.get("/beers/barcode/?code=5410908000036")
            client.get("/beers/barcode/?code=5410908000036")
            assert search.call_count == 1

    def test_fields_param_trims_payload(self) -> None:
        client = APIClient()
        BeerFactory(vmp_id=3246802)
        with patch("beers.api.views.VmpClient.from_external_api") as mock_factory:
            mock_factory.return_value.barcode_search.return_value = "3246802"
            response = client.get(
                "/beers/barcode/?code=5410908000036&fields=vmp_id,vmp_name"
            )
        assert set(response.data.keys()) == {"vmp_id", "vmp_name"}


@pytest.mark.django_db
class TestExtensionTokenView:
    def test_get_creates_and_returns_token(self, auth_client: tuple) -> None:
        client, user = auth_client
        response = client.get("/auth/extension-token/")
        assert response.status_code == 200
        assert response.data["token"] == Token.objects.get(user=user).key

    def test_get_is_idempotent(self, auth_client: tuple) -> None:
        client, _user = auth_client
        first = client.get("/auth/extension-token/").data["token"]
        second = client.get("/auth/extension-token/").data["token"]
        assert first == second

    def test_delete_revokes_token(self, auth_client: tuple) -> None:
        client, user = auth_client
        client.get("/auth/extension-token/")
        response = client.delete("/auth/extension-token/")
        assert response.status_code == 204
        assert not Token.objects.filter(user=user).exists()

    def test_unauthenticated_returns_401(self) -> None:
        client = APIClient()
        response = client.get("/auth/extension-token/")
        assert response.status_code in (401, 403)
