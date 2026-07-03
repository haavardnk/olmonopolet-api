import pytest
from beers.models import Tasted
from beers.tests.factories import BeerFactory, UserFactory
from rest_framework.test import APIClient


@pytest.fixture
def auth_client() -> tuple[APIClient, any]:
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestMarkTasted:
    def test_mark_tasted_creates_record(self, auth_client: tuple) -> None:
        client, user = auth_client
        beer = BeerFactory()
        response = client.post(f"/beers/{beer.pk}/mark_tasted/")
        assert response.status_code == 201
        assert Tasted.objects.filter(user=user, beer=beer).exists()

    def test_mark_tasted_idempotent(self, auth_client: tuple) -> None:
        client, user = auth_client
        beer = BeerFactory()
        Tasted.objects.create(user=user, beer=beer)
        response = client.post(f"/beers/{beer.pk}/mark_tasted/")
        assert response.status_code == 200

    def test_unmark_tasted_deletes_record(self, auth_client: tuple) -> None:
        client, user = auth_client
        beer = BeerFactory()
        Tasted.objects.create(user=user, beer=beer)
        response = client.delete(f"/beers/{beer.pk}/mark_tasted/")
        assert response.status_code == 204
        assert not Tasted.objects.filter(user=user, beer=beer).exists()

    def test_unmark_tasted_not_found(self, auth_client: tuple) -> None:
        client, _user = auth_client
        beer = BeerFactory()
        response = client.delete(f"/beers/{beer.pk}/mark_tasted/")
        assert response.status_code == 404

    def test_mark_tasted_unauthenticated(self) -> None:
        client = APIClient()
        beer = BeerFactory()
        response = client.post(f"/beers/{beer.pk}/mark_tasted/")
        assert response.status_code in (401, 403)

    def test_user_tasted_annotation(self, auth_client: tuple) -> None:
        client, user = auth_client
        beer = BeerFactory()
        Tasted.objects.create(user=user, beer=beer)
        response = client.get(f"/beers/{beer.pk}/")
        assert response.data["user_tasted"] is True

    def test_user_tasted_annotation_false(self, auth_client: tuple) -> None:
        client, _user = auth_client
        beer = BeerFactory()
        response = client.get(f"/beers/{beer.pk}/")
        assert response.data["user_tasted"] is False
