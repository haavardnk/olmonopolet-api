from __future__ import annotations

from beers.api.utils import get_or_create_country
from beers.models import Beer
from beers.vmp import VmpApiError, VmpClient
from beers.vmp.models import VmpProduct
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

CATEGORIES: list[tuple[str, str | None]] = [
    ("øl", None),
    ("sider", None),
    ("mjød", None),
    ("alkoholfritt", "alkoholfritt_alkoholfritt_øl"),
    ("alkoholfritt", "alkoholfritt_alkoholfri_ingefærøl"),
    ("alkoholfritt", "alkoholfritt_alkoholfri_sider"),
]

VMP_BASE_URL = "https://www.vinmonopolet.no"
ALL_STORES_DELIVERY = "Kan bestilles til alle butikker"


class VmpCommand(BaseCommand):
    def get_client(
        self, request_delay: tuple[float, float] | None = None
    ) -> VmpClient:
        try:
            return VmpClient.from_external_api(request_delay)
        except VmpApiError as exc:
            raise CommandError(str(exc)) from exc


def post_delivery(product: VmpProduct) -> bool:
    availability = product.product_availability
    if availability is None or availability.delivery_availability is None:
        return False
    return bool(availability.delivery_availability.available_for_purchase)


def store_delivery(product: VmpProduct) -> bool:
    availability = product.product_availability
    if availability is None or availability.stores_availability is None:
        return False
    return any(
        info.readable_value == ALL_STORES_DELIVERY
        for info in availability.stores_availability.infos
    )


def apply_product_fields(beer: Beer, product: VmpProduct) -> None:
    beer.vmp_name = product.name
    beer.main_category = product.main_category.name
    if product.main_sub_category:
        beer.sub_category = product.main_sub_category.name
    beer.country = get_or_create_country(product.main_country.name)
    beer.volume = product.volume.value / 100.0
    if product.price is not None:
        beer.price = product.price.value
    beer.product_selection = product.product_selection
    beer.vmp_url = f"{VMP_BASE_URL}{product.url}"
    beer.vmp_updated = timezone.now()
    if not beer.active:
        beer.active = True
