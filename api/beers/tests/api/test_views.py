import io
import pytest
from beers.models import Badge, Beer, Stock, Store, Tasted, UserList, UserListItem
from beers.tests.factories import BeerFactory, CountryFactory, StockFactory, StoreFactory, UserFactory
from django.utils import timezone
from rest_framework.test import APIClient


@pytest.fixture
def auth_client() -> tuple[APIClient, any]:
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


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
        self, auth_client: tuple, file_data: bytes | None, file_name: str | None, error_fragment: str
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
class TestBeerPrefetch:
    def test_stock_prefetch(self, auth_client: tuple) -> None:
        client, _user = auth_client
        beer = BeerFactory()
        store = StoreFactory(store_id=500)
        StockFactory(store=store, beer=beer, quantity=5)
        response = client.get(f"/beers/{beer.pk}/?store=500")
        assert response.status_code == 200
        assert response.data["stock"] == 5

    def test_badge_prefetch(self, auth_client: tuple) -> None:
        client, _user = auth_client
        beer = BeerFactory()
        Badge.objects.create(beer=beer, text="New", type="info")
        response = client.get(f"/beers/{beer.pk}/")
        assert response.status_code == 200
        assert response.data["badges"][0]["text"] == "New"


@pytest.mark.django_db
class TestStockChangeUserTasted:
    @pytest.mark.parametrize("tasted,expected", [(True, True), (False, False)], ids=["tasted", "not-tasted"])
    def test_user_tasted_annotation(self, auth_client: tuple, tasted: bool, expected: bool) -> None:
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
class TestUserListSortOrder:
    def test_sort_order_auto_increments(self, auth_client: tuple) -> None:
        client, user = auth_client
        client.post("/lists/", {"name": "First"})
        client.post("/lists/", {"name": "Second"})
        first = UserList.objects.get(user=user, name="First")
        second = UserList.objects.get(user=user, name="Second")
        assert first.sort_order == 1
        assert second.sort_order == 2


@pytest.mark.django_db
class TestUserListAddItem:
    def test_add_item_success(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        response = client.post(f"/lists/{user_list.pk}/items/", {"product_id": str(beer.vmp_id)})
        assert response.status_code == 201
        assert UserListItem.objects.filter(list=user_list, product_id=str(beer.vmp_id)).exists()

    def test_add_item_duplicate_returns_409(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(user=user, name="Test", sort_order=1)
        beer = BeerFactory()
        UserListItem.objects.create(list=user_list, product_id=str(beer.vmp_id), sort_order=1)
        response = client.post(f"/lists/{user_list.pk}/items/", {"product_id": str(beer.vmp_id)})
        assert response.status_code == 409

    def test_add_item_to_untappd_list_blocked(self, auth_client: tuple) -> None:
        client, user = auth_client
        user_list = UserList.objects.create(
            user=user, name="Untappd", sort_order=1, list_type=UserList.ListType.UNTAPPD
        )
        beer = BeerFactory()
        response = client.post(f"/lists/{user_list.pk}/items/", {"product_id": str(beer.vmp_id)})
        assert response.status_code == 403
