from __future__ import annotations

from argparse import ArgumentParser
from typing import Any

from beers.models import Beer, Release
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--name", type=str, required=True)
        parser.add_argument("--products", type=str, required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        name = options["name"]
        products = options["products"]

        release = self._get_or_create_release(name)
        beer_count = self._add_beers_to_release(release, products)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created release with name: {name} and added {beer_count} beers."
            )
        )

    def _get_or_create_release(self, name: str) -> Release:
        release, _ = Release.objects.get_or_create(name=name)
        return release

    def _add_beers_to_release(self, release: Release, products: str) -> int:
        beer_count = 0

        for product_id in products.split(","):
            product_id = product_id.strip()
            if not product_id:
                continue

            beer = self._get_beer(product_id)
            if beer is None:
                continue

            release.beer.add(beer)
            beer_count += 1

        return beer_count

    def _get_beer(self, product_id: str) -> Beer | None:
        try:
            return Beer.objects.get(vmp_id=int(product_id))
        except (Beer.DoesNotExist, ValueError):
            return None
