import io

import pytest
import responses
from beers.models import Beer, Country, ExternalAPI
from beers.vmp.commands import apply_product_fields, post_delivery, store_delivery
from beers.vmp.models import VmpProduct
from django.core.management import call_command

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


def beer_product(**overrides) -> VmpProduct:
    return VmpProduct.model_validate({**BEER_DATA, **overrides})


@pytest.fixture(autouse=True)
def setup(db):
    ExternalAPI.objects.create(
        name="vinmonopolet_v2", baseurl="https://api.test.com/v2/"
    )
    ExternalAPI.objects.create(
        name="vinmonopolet_v3", baseurl="https://api.test.com/v3/"
    )


class TestApplyProductFields:
    def test_sets_fields(self, db):
        beer = Beer(vmp_id=9999)
        apply_product_fields(beer, beer_product())
        beer.save()

        beer.refresh_from_db()
        assert beer.vmp_name == "Test IPA"
        assert beer.main_category == "Øl"
        assert beer.sub_category == "India Pale Ale"
        assert beer.price == 59.90
        assert beer.volume == 0.5
        assert beer.product_selection == "Basisutvalget"
        assert beer.vmp_url == "https://www.vinmonopolet.no/p/9999"
        assert beer.vmp_updated is not None

    def test_country_is_fk(self, db):
        beer = Beer(vmp_id=9999)
        apply_product_fields(beer, beer_product())

        assert isinstance(beer.country, Country)
        assert beer.country.name == "Norge"

    def test_without_sub_category(self, db):
        beer = Beer(vmp_id=9999)
        apply_product_fields(beer, beer_product(main_sub_category=None))

        assert beer.sub_category is None

    def test_price_per_volume(self, db):
        beer = Beer(vmp_id=9999)
        apply_product_fields(beer, beer_product())
        beer.save()
        beer.refresh_from_db()

        assert beer.price_per_volume is not None
        assert abs(beer.price_per_volume - (59.90 / 0.5)) < 0.01

    def test_without_price_skips_price(self, db):
        beer = Beer(vmp_id=9999)
        apply_product_fields(beer, beer_product(price=None))
        beer.save()
        beer.refresh_from_db()

        assert beer.price is None
        assert beer.price_per_volume is None

    def test_reactivates_inactive_beer(self, db):
        beer = Beer(vmp_id=9999, active=False)
        apply_product_fields(beer, beer_product())

        assert beer.active is True


class TestDelivery:
    def test_post_and_store_delivery_true(self):
        product = beer_product()
        assert post_delivery(product) is True
        assert store_delivery(product) is True

    def test_delivery_false_without_availability(self):
        product = beer_product(productAvailability=None)
        assert post_delivery(product) is False
        assert store_delivery(product) is False


class TestFullFlow:
    @responses.activate
    def test_handle_creates_beer(self, db):
        responses.add(
            responses.GET,
            "https://api.test.com/v2/products/search",
            json={"products": [BEER_DATA], "pagination": {"totalPages": 1}},
            status=200,
        )

        call_command("update_beers_from_vmp", stdout=io.StringIO())

        assert Beer.objects.filter(vmp_id=9999).exists()

    @responses.activate
    def test_handle_skips_product_without_price(self, db):
        responses.add(
            responses.GET,
            "https://api.test.com/v2/products/search",
            json={
                "products": [{**BEER_DATA, "price": None}],
                "pagination": {"totalPages": 1},
            },
            status=200,
        )

        call_command("update_beers_from_vmp", stdout=io.StringIO())

        assert not Beer.objects.filter(vmp_id=9999).exists()
