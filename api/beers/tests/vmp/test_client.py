import pytest
import responses
from beers.models import ExternalAPI
from beers.vmp import VmpApiError, VmpBlockedError, VmpClient

from .test_models import DETAIL_JSON, PRODUCT_JSON, SEARCH_JSON, STORE_JSON

V2 = "https://api.test.com/v2/"
V3 = "https://api.test.com/v3/"


@pytest.fixture
def client() -> VmpClient:
    return VmpClient(V2, V3)


class TestFromExternalApi:
    def test_reads_both_baseurls(self, db):
        ExternalAPI.objects.create(name="vinmonopolet_v2", baseurl=V2)
        ExternalAPI.objects.create(name="vinmonopolet_v3", baseurl=V3)

        client = VmpClient.from_external_api()

        assert client._v2 == V2
        assert client._v3 == V3

    def test_missing_config_raises(self, db):
        with pytest.raises(VmpApiError):
            VmpClient.from_external_api()


class TestSearch:
    @responses.activate
    def test_search_returns_products(self, client):
        responses.add(
            responses.GET, f"{V2}products/search", json=SEARCH_JSON, status=200
        )

        result = client.search("øl")

        assert result.products[0].code == "1234"
        assert result.pagination.total_pages == 3

    @responses.activate
    def test_iter_products_paginates(self, client):
        responses.add(
            responses.GET,
            f"{V2}products/search",
            json={"products": [PRODUCT_JSON], "pagination": {"totalPages": 2}},
            status=200,
        )

        products = list(client.iter_products("øl"))

        assert len(products) == 2


class TestGetProduct:
    @responses.activate
    def test_returns_detail(self, client):
        responses.add(responses.GET, f"{V3}products/1234", json=DETAIL_JSON, status=200)

        detail = client.get_product(1234)

        assert detail.code == "1234"
        assert detail.color == "Gyllen"


class TestGetStore:
    @responses.activate
    def test_returns_store(self, client):
        responses.add(responses.GET, f"{V2}stores/116", json=STORE_JSON, status=200)

        store = client.get_store("116")

        assert store.display_name == "Oslo, Aker Brygge"


class TestStoreFacets:
    @responses.activate
    def test_returns_facet_values(self, client):
        responses.add(
            responses.GET, f"{V2}products/search", json=SEARCH_JSON, status=200
        )

        facets = client.iter_store_facets()

        assert facets[0].code == "116"

    @responses.activate
    def test_missing_facet_raises(self, client):
        responses.add(
            responses.GET,
            f"{V2}products/search",
            json={"products": [], "pagination": {"totalPages": 0}, "facets": []},
            status=200,
        )

        with pytest.raises(VmpApiError):
            client.iter_store_facets()


class TestBarcodeSearch:
    @responses.activate
    def test_found(self, client):
        responses.add(
            responses.GET,
            f"{V2}products/barCodeSearch/123",
            json=PRODUCT_JSON,
            status=200,
        )

        product = client.barcode_search("123")

        assert product is not None
        assert product.code == "1234"

    @responses.activate
    def test_not_found_returns_none(self, client):
        responses.add(
            responses.GET, f"{V2}products/barCodeSearch/123", json={}, status=400
        )

        assert client.barcode_search("123") is None


class TestFetchRetry:
    @responses.activate
    def test_raises_after_failures(self, client):
        responses.add(responses.GET, f"{V2}products/search", json={}, status=500)

        with pytest.raises(VmpApiError):
            client.search("øl")


class TestBlocked:
    @pytest.mark.parametrize("status", [403, 429, 503])
    @responses.activate
    def test_fetch_aborts_on_block_without_retry(self, client, status):
        responses.add(
            responses.GET, f"{V2}products/search", json={}, status=status
        )

        with pytest.raises(VmpBlockedError):
            client.search("øl")

        assert len(responses.calls) == 1

    @responses.activate
    def test_barcode_search_aborts_on_block(self, client):
        responses.add(
            responses.GET, f"{V2}products/barCodeSearch/123", json={}, status=403
        )

        with pytest.raises(VmpBlockedError):
            client.barcode_search("123")

        assert len(responses.calls) == 1
