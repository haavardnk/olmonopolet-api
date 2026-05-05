import io
import pytest
from beers.models import (
    Badge,
    Stock,
    Tasted,
    UserList,
    UserListItem,
)
from beers.tests.factories import (
    BeerFactory,
    CountryFactory,
    StockFactory,
    StoreFactory,
    UserFactory,
)
from django.utils import timezone
from rest_framework.test import APIClient


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
        user_list = UserList.objects.create(
            user=user, name="Untappd", sort_order=1, list_type=UserList.ListType.UNTAPPD
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
