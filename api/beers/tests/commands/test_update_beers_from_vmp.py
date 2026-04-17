import cloudscraper25
import pytest
import responses
from beers.management.commands.update_beers_from_vmp import Command
from beers.models import Beer, Country, ExternalAPI

BEER_DATA = {
    "code": "9999",
    "name": "Test IPA",
    "main_category": {"name": "Øl"},
    "main_sub_category": {"name": "India Pale Ale"},
    "main_country": {"name": "Norge"},
    "price": {"value": 59.90},
    "volume": {"value": 50},
    "product_selection": "Basisutvalget",
    "url": "/p/9999",
    "productAvailability": {
        "deliveryAvailability": {"availableForPurchase": True},
        "storesAvailability": {
            "infos": [{"readableValue": "Kan bestilles til alle butikker"}]
        },
    },
}


@pytest.fixture(autouse=True)
def setup(db):
    ExternalAPI.objects.create(
        name="vinmonopolet",
        baseurl="https://api.test.com/v4/",
    )


class TestCreateNewBeer:
    def test_creates_beer_with_correct_fields(self, db):
        cmd = Command()
        beer = cmd._create_new_beer(BEER_DATA)

        assert beer.vmp_id == 9999
        assert beer.vmp_name == "Test IPA"
        assert beer.main_category == "Øl"
        assert beer.sub_category == "India Pale Ale"
        assert beer.price == 59.90
        assert beer.volume == 0.5
        assert beer.product_selection == "Basisutvalget"
        assert beer.vmp_url == "https://www.vinmonopolet.no/p/9999"
        assert beer.post_delivery is True
        assert beer.store_delivery is True
        assert beer.vmp_updated is not None

    def test_creates_country_as_fk(self, db):
        cmd = Command()
        beer = cmd._create_new_beer(BEER_DATA)

        assert isinstance(beer.country, Country)
        assert beer.country.name == "Norge"
        assert Country.objects.filter(name="Norge").exists()

    def test_without_sub_category(self, db):
        data = {**BEER_DATA, "main_sub_category": None}
        cmd = Command()
        beer = cmd._create_new_beer(data)

        assert beer.sub_category is None

    def test_price_per_volume(self, db):
        cmd = Command()
        beer = cmd._create_new_beer(BEER_DATA)

        expected = 59.90 / 0.5
        if beer.price_per_volume is None:
            raise ValueError("price_per_volume should not be None")
        assert abs(beer.price_per_volume - expected) < 0.01

    @responses.activate
    def test_full_flow_creates_beer(self):
        response_data = {
            "products": [BEER_DATA],
            "pagination": {"totalPages": 1},
        }
        responses.add(
            responses.GET,
            "https://api.test.com/v4/products/search",
            json=response_data,
            status=200,
        )

        cmd = Command()
        cmd.stdout = __import__("io").StringIO()

        scraper = cloudscraper25.create_scraper()

        updated, created = cmd._process_product_category(
            scraper, "https://api.test.com/v4/products/search", "øl"
        )

        assert created == 1
        assert updated == 0
        assert Beer.objects.filter(vmp_id=9999).exists()
