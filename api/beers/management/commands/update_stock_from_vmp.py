from __future__ import annotations

import re
import time
from argparse import ArgumentParser

from beers.models import Beer, Stock, Store
from beers.vmp import VmpApiError, VmpClient
from beers.vmp.commands import CATEGORIES, VmpCommand
from beers.vmp.models import VmpProduct
from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone


class Command(VmpCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("stores", type=int, help="Number of stores to process")
        parser.add_argument(
            "--store-delay",
            type=float,
            default=0,
            help="Seconds to pause between stores to reduce rate-limiting",
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

        stores = Store.objects.all().order_by("store_stock_updated")[
            : options["stores"]
        ]

        if not stores:
            self.stdout.write(self.style.WARNING("No stores found to update"))
            return

        store_delay = options["store_delay"]
        self.stdout.write(f"Processing {len(stores)} stores...")

        updated = 0
        stocked = 0
        unstocked = 0
        stores_updated = 0
        failed: list[str] = []

        for index, store in enumerate(stores.iterator()):
            if index and store_delay and not settings.TESTING:
                time.sleep(store_delay)
            try:
                store_updated, store_stocked, store_unstocked = (
                    self._update_store_stock(client, store)
                )
            except VmpApiError as exc:
                failed.append(store.name)
                self.stdout.write(
                    self.style.WARNING(f"Store {store.name} not updated: {exc}")
                )
                continue

            updated += store_updated
            stocked += store_stocked
            unstocked += store_unstocked
            stores_updated += 1

            self.stdout.write(
                f"Store {store.name}: Updated {store_updated}, Stocked {store_stocked}, "
                f"Unstocked {store_unstocked} | Total: {stores_updated}/{len(stores)}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated stock: {updated} Stocked: {stocked} "
                f"Out of stock: {unstocked} Stores updated: {stores_updated}/{len(stores)}"
            )
        )

        if failed:
            raise CommandError(
                f"{len(failed)}/{len(stores)} stores failed: {', '.join(failed)}"
            )

    def _update_store_stock(
        self, client: VmpClient, store: Store
    ) -> tuple[int, int, int]:
        updated = 0
        stocked = 0
        stocked_beers: list[Beer] = []

        for category, sub_category in CATEGORIES:
            products = client.iter_products(
                category, sub_category, store_id=store.store_id
            )
            category_products = list(products)

            for product in category_products:
                try:
                    beer = Beer.objects.get(vmp_id=int(product.code))
                except Beer.DoesNotExist:
                    continue

                stocked_beers.append(beer)

                quantity = self._extract_quantity(product)
                beer_updated, beer_stocked = self._update_beer_stock(
                    store, beer, quantity
                )
                updated += beer_updated
                stocked += beer_stocked

        unstocked = 0
        if stocked_beers:
            unstocked = self._unstock_missing_beers(store, stocked_beers)

        store.store_stock_updated = timezone.now()
        store.save()

        return updated, stocked, unstocked

    def _extract_quantity(self, product: VmpProduct) -> int:
        availability = product.product_availability
        if availability is None or availability.stores_availability is None:
            return 0

        for info in availability.stores_availability.infos:
            quantities = re.findall(r"\b\d+\b", info.availability or "")
            if quantities:
                return int(quantities[0])
        return 0

    def _update_beer_stock(
        self, store: Store, beer: Beer, quantity: int
    ) -> tuple[int, int]:
        try:
            stock = Stock.objects.get(store=store, beer=beer)
            if stock.quantity == 0 and quantity != 0:
                stock.stocked_at = timezone.now()
            stock.quantity = quantity
            stock.save()
            return 1, 0

        except Stock.DoesNotExist:
            Stock.objects.create(
                store=store,
                beer=beer,
                quantity=quantity,
                stocked_at=timezone.now(),
            )
            return 0, 1

    def _unstock_missing_beers(self, store: Store, stocked_beers: list[Beer]) -> int:
        stocks_to_unstock = (
            Stock.objects.filter(store=store)
            .exclude(beer__in=stocked_beers)
            .exclude(quantity=0)
        )

        count = stocks_to_unstock.count()

        for stock in stocks_to_unstock:
            stock.quantity = 0
            stock.unstocked_at = timezone.now()
            stock.save()

        return count
