from __future__ import annotations

import time
from argparse import ArgumentParser

from beers.models import Beer
from beers.vmp.commands import (
    CATEGORIES,
    VmpCommand,
    apply_product_fields,
    post_delivery,
    store_delivery,
)
from beers.vmp.models import VmpProduct
from django.conf import settings
from django.core.management.base import CommandError


class Command(VmpCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--category",
            type=str,
            default=None,
            help="Only process this main category (e.g. øl) to stagger the crawl",
        )
        parser.add_argument(
            "--store-delay",
            type=float,
            default=0,
            help="Seconds to pause between categories to reduce rate-limiting",
        )
        parser.add_argument(
            "--request-delay-min",
            type=float,
            default=0.5,
            help="Minimum seconds to pause between requests",
        )
        parser.add_argument(
            "--request-delay-max",
            type=float,
            default=1.5,
            help="Maximum seconds to pause between requests",
        )

    def handle(self, *args, **options) -> None:
        client = self.get_client(
            (options["request_delay_min"], options["request_delay_max"])
        )

        store_delay = options["store_delay"]
        categories = self._select_categories(options["category"])

        updated = 0
        created = 0
        skipped = 0

        for index, (category, sub_category) in enumerate(categories):
            if index and store_delay and not settings.TESTING:
                time.sleep(store_delay)
            for product in client.iter_products(
                category, sub_category, sort="relevance"
            ):
                code = int(product.code)
                try:
                    beer = Beer.objects.get(vmp_id=code)
                    is_new = False
                except Beer.DoesNotExist:
                    beer = Beer(vmp_id=code)
                    is_new = True

                if not self._save_beer(beer, product):
                    skipped += 1
                elif is_new:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers, created {created} new beers, "
                f"skipped {skipped} without price!"
            )
        )

    def _select_categories(self, category: str | None) -> list[tuple[str, str | None]]:
        if category is None:
            return CATEGORIES
        selected = [entry for entry in CATEGORIES if entry[0] == category]
        if not selected:
            available = sorted({entry[0] for entry in CATEGORIES})
            raise CommandError(
                f"unknown category '{category}', choose from: {', '.join(available)}"
            )
        return selected

    def _save_beer(self, beer: Beer, product: VmpProduct) -> bool:
        if product.price is None:
            return False
        apply_product_fields(beer, product)
        beer.post_delivery = post_delivery(product)
        beer.store_delivery = store_delivery(product)
        beer.save()
        return True
