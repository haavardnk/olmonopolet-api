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
