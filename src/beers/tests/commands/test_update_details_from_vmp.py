import pytest

from beers.management.commands.update_details_from_vmp import Command
from beers.models import Beer
from beers.tests.factories import BeerFactory
from clients.vmp.models import VmpProductDetail

PRODUCT = {
    "code": "1",
    "name": "Test",
    "url": "/p/1",
    "volume": {"value": 50},
    "main_category": {"name": "Øl"},
    "main_country": {"name": "Norge"},
}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("vmp_value", "expected"),
    [
        ("Glass", Beer.PackageType.BOTTLE),
        ("Metall", Beer.PackageType.CAN),
        ("Emballasje med pant", Beer.PackageType.CAN),
        ("Bag-in-box", Beer.PackageType.OTHER),
        ("Ukjent", Beer.PackageType.OTHER),
    ],
)
def test_sets_package_type(vmp_value: str, expected: Beer.PackageType) -> None:
    beer = BeerFactory(vmp_id=1)
    detail = VmpProductDetail.model_validate({**PRODUCT, "packageType": vmp_value})

    Command()._update_product_details(beer, detail)

    beer.refresh_from_db()
    assert beer.package_type == expected


@pytest.mark.django_db
def test_sets_facet_fields() -> None:
    beer = BeerFactory(vmp_id=1)
    detail = VmpProductDetail.model_validate(
        {
            **PRODUCT,
            "packageType": "Emballasje med pant",
            "eco": False,
            "gluten": True,
            "environmentalPackaging": True,
            "ageLimit": 18,
            "main_producer": {"code": "jåttå", "name": "Jåttå"},
            "main_wholesaler": {"code": "Jåttå AS", "name": "Jåttå AS"},
            "content": {
                "isGoodFor": [
                    {"code": "D", "name": "Lyst kjøtt"},
                    {"code": "Q", "name": "Svin"},
                ]
            },
        }
    )

    Command()._update_product_details(beer, detail)

    beer.refresh_from_db()
    assert beer.package_material == "Emballasje med pant"
    assert beer.eco is False
    assert beer.gluten_free is True
    assert beer.climate_smart_packaging is True
    assert beer.age_limit == 18
    assert beer.producer_code == "jåttå"
    assert beer.wholesaler == "Jåttå AS"
    assert beer.food_pairing_codes == ["D", "Q"]
