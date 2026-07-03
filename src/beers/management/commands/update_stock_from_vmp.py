from __future__ import annotations

import re
import time
from argparse import ArgumentParser

from beers.models import Beer, Stock, Store
from beers.vmp import VmpApiError, VmpBlockedError, VmpClient, circuit_breaker
from beers.vmp.commands import CATEGORIES, VmpCommand
from beers.vmp.models import VmpProduct
from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone


class Command(VmpCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("stores", type=int, help="Number of stores to process")
        parser.add_argument(
            "--max-requests",
            type=int,
            default=20,
            help="Maximum search pages to fetch across all stores this run",
        )
        parser.add_argument(
            "--circuit-breaker-cooldown",
            type=int,
            default=7200,
            help="Seconds to keep the circuit breaker open after a block",
        )
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
        if circuit_breaker.is_open():
            self.stdout.write(
                self.style.WARNING(
                    f"Circuit breaker open, skipping run "
                    f"({circuit_breaker.seconds_remaining()}s remaining)"
                )
            )
            return

        client = self.get_client(
            (options["request_delay_min"], options["request_delay_max"])
        )

        candidate_ids = self._candidate_store_ids(options["stores"])
        if not candidate_ids:
            self.stdout.write(self.style.WARNING("No stores found to update"))
            return

        store_delay = options["store_delay"]
        budget = options["max_requests"]
        cooldown = options["circuit_breaker_cooldown"]
        self.stdout.write(
            f"Processing up to {len(candidate_ids)} stores, budget {budget} pages..."
        )

        updated = 0
        stocked = 0
        unstocked = 0
        stores_completed = 0
        failed: list[str] = []

        for index, store_id in enumerate(candidate_ids):
            if budget <= 0:
                break
            if index and store_delay and not settings.TESTING:
                time.sleep(store_delay)

            store = self._claim_store(store_id)
            if store is None:
                continue

            try:
                consumed, store_updated, store_stocked, store_unstocked, completed = (
                    self._sync_store(client, store, budget)
                )
            except VmpBlockedError as exc:
                circuit_breaker.open(cooldown)
                raise CommandError(str(exc)) from exc
            except VmpApiError as exc:
                failed.append(store.name)
                self.stdout.write(
                    self.style.WARNING(f"Store {store.name} not updated: {exc}")
                )
                continue

            budget -= consumed
            updated += store_updated
            stocked += store_stocked
            unstocked += store_unstocked
            if completed:
                stores_completed += 1

            self.stdout.write(
                f"Store {store.name}: Updated {store_updated}, Stocked {store_stocked}, "
                f"Unstocked {store_unstocked}, Pages {consumed}, "
                f"{'complete' if completed else 'paused'}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated stock: {updated} Stocked: {stocked} "
                f"Out of stock: {unstocked} Stores completed: {stores_completed}"
            )
        )

        if failed:
            raise CommandError(f"{len(failed)} stores failed: {', '.join(failed)}")

    def _candidate_store_ids(self, limit: int) -> list[int]:
        in_progress = list(
            Store.objects.filter(stock_sync_started__isnull=False)
            .order_by("stock_sync_started")
            .values_list("store_id", flat=True)
        )
        idle = list(
            Store.objects.filter(stock_sync_started__isnull=True)
            .order_by("store_stock_updated")
            .values_list("store_id", flat=True)
        )
        return (in_progress + idle)[:limit]

    def _claim_store(self, store_id: int) -> Store | None:
        with transaction.atomic():
            store = (
                Store.objects.select_for_update(skip_locked=True)
                .filter(pk=store_id)
                .first()
            )
            if store is None:
                return None
            if store.stock_sync_started is None:
                store.stock_sync_started = timezone.now()
                store.stock_sync_category = 0
                store.stock_sync_page = 0
                store.save()
            return store

    def _sync_store(
        self, client: VmpClient, store: Store, budget: int
    ) -> tuple[int, int, int, int, bool]:
        consumed = 0
        updated = 0
        stocked = 0
        cat_index = store.stock_sync_category
        page = store.stock_sync_page

        while cat_index < len(CATEGORIES):
            if consumed >= budget:
                store.stock_sync_category = cat_index
                store.stock_sync_page = page
                store.save()
                return consumed, updated, stocked, 0, False

            store.stock_sync_category = cat_index
            store.stock_sync_page = page
            store.save()

            category, sub_category = CATEGORIES[cat_index]
            response = client.search(
                category, sub_category, store_id=store.store_id, page=page
            )
            consumed += 1

            for product in response.products:
                try:
                    beer = Beer.objects.get(vmp_id=int(product.code))
                except Beer.DoesNotExist:
                    continue
                quantity = self._extract_quantity(product)
                beer_updated, beer_stocked = self._update_beer_stock(
                    store, beer, quantity
                )
                updated += beer_updated
                stocked += beer_stocked

            if page + 1 < response.pagination.total_pages:
                page += 1
            else:
                cat_index += 1
                page = 0

        unstocked = self._unstock_missing_beers(store)
        store.store_stock_updated = timezone.now()
        store.stock_sync_started = None
        store.stock_sync_category = 0
        store.stock_sync_page = 0
        store.save()

        return consumed, updated, stocked, unstocked, True

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
        seen = store.stock_sync_started
        try:
            stock = Stock.objects.get(store=store, beer=beer)
            if stock.quantity == 0 and quantity != 0:
                stock.stocked_at = timezone.now()
            stock.quantity = quantity
            stock.last_seen_in_stock_sync = seen
            stock.save()
            return 1, 0

        except Stock.DoesNotExist:
            Stock.objects.create(
                store=store,
                beer=beer,
                quantity=quantity,
                stocked_at=timezone.now(),
                last_seen_in_stock_sync=seen,
            )
            return 0, 1

    def _unstock_missing_beers(self, store: Store) -> int:
        stocks_to_unstock = (
            Stock.objects.filter(store=store)
            .exclude(quantity=0)
            .filter(
                Q(last_seen_in_stock_sync__lt=store.stock_sync_started)
                | Q(last_seen_in_stock_sync__isnull=True)
            )
        )

        count = stocks_to_unstock.count()

        for stock in stocks_to_unstock:
            stock.quantity = 0
            stock.unstocked_at = timezone.now()
            stock.save()

        return count
