from __future__ import annotations

from argparse import ArgumentParser

from beers.models import Beer
from beers.vmp import VmpApiError
from beers.vmp.commands import VmpCommand
from beers.vmp.models import VmpProductDetail
from django.core.management.base import CommandError
from django.utils import timezone

CHARACTERISTIC_FIELDS = {
    "Fylde": "fullness",
    "Sødme": "sweetness",
    "Friskhet": "freshness",
    "Bitterhet": "bitterness",
}


class Command(VmpCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("calls", type=int, help="Number of beers to process")

    def handle(self, *args, **options) -> None:
        client = self.get_client()

        products_without_details = Beer.objects.filter(
            active=True, vmp_details_fetched=None
        )
        products = products_without_details[: options["calls"]]

        if not products:
            self.stdout.write(
                self.style.WARNING("No products found that need detail updates")
            )
            return

        self.stdout.write(f"Processing {len(products)} products...")

        updated = 0
        failed = 0

        for product in products:
            try:
                detail = client.get_product(product.vmp_id)
            except VmpApiError:
                failed += 1
                continue
            self._update_product_details(product, detail)
            updated += 1

        remaining = products_without_details.count() - len(products)
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers and failed to update {failed} beers. "
                f"{remaining} products still need details."
            )
        )

        if failed and updated == 0:
            raise CommandError(
                f"All {failed} detail lookups failed (vinmonopolet unreachable)"
            )

    def _update_product_details(self, beer: Beer, detail: VmpProductDetail) -> None:
        if detail.producer is not None:
            beer.vmp_brewery = detail.producer.name
        if detail.color is not None:
            beer.color = detail.color
        if detail.smell is not None:
            beer.aroma = detail.smell
        if detail.taste is not None:
            beer.taste = detail.taste
        if detail.allergens is not None:
            beer.allergens = detail.allergens
        if detail.method is not None:
            beer.method = detail.method

        content = detail.content
        if content is not None:
            for char in content.characteristics:
                field = CHARACTERISTIC_FIELDS.get(char.name or "")
                if field:
                    setattr(beer, field, char.value)

            if content.storage_potential is not None:
                beer.storable = content.storage_potential.formatted_value or ""

            if content.ingredients:
                beer.raw_materials = content.ingredients[0].formatted_value or ""

            if content.is_good_for:
                beer.food_pairing = ", ".join(food.name for food in content.is_good_for)

        if detail.vintage is not None:
            beer.year = detail.vintage
        elif detail.year is not None:
            beer.year = detail.year

        if detail.sugar is not None:
            beer.sugar = self._parse_sugar_value(detail.sugar)
        if detail.acid is not None:
            beer.acid = self._parse_acid_value(detail.acid)

        beer.vmp_details_fetched = timezone.now()
        beer.save()

    def _parse_sugar_value(self, sugar_str: str) -> float:
        return float(sugar_str.replace("<", "").replace(",", ".").split(" ")[-1])

    def _parse_acid_value(self, acid_str: str) -> float:
        return float(acid_str.replace(",", "."))
