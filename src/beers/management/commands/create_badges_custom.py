from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand

from beers.models import Badge, Beer

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from typing import Any


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--products", type=str, required=True)
        parser.add_argument("--badge_text", type=str, required=True)
        parser.add_argument("--badge_type", type=str, required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        products = options["products"]
        badge_text = options["badge_text"]
        badge_type = options["badge_type"]

        created_count = self._create_badges(products, badge_text, badge_type)

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} badges."))

    def _create_badges(self, products: str, badge_text: str, badge_type: str) -> int:
        created_count = 0

        for product_id in products.split(","):
            product_id = product_id.strip()
            if not product_id:
                continue

            beer = self._get_beer(product_id)
            if beer is None:
                continue

            _badge, created = Badge.objects.get_or_create(
                beer=beer, text=badge_text, defaults={"type": badge_type}
            )
            if created:
                created_count += 1

        return created_count

    def _get_beer(self, product_id: str) -> Beer | None:
        try:
            return Beer.objects.get(vmp_id=int(product_id))
        except (Beer.DoesNotExist, ValueError):
            return None
