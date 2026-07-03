from __future__ import annotations

from argparse import ArgumentParser

from beers.models import Beer, VmpCrawlState
from beers.vmp import VmpBlockedError, circuit_breaker
from beers.vmp.commands import (
    CATEGORIES,
    VmpCommand,
    apply_product_fields,
    post_delivery,
    store_delivery,
)
from beers.vmp.models import VmpProduct
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone


class Command(VmpCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--category",
            type=str,
            default=None,
            help="Only process this main category (e.g. øl) to stagger the crawl",
        )
        parser.add_argument(
            "--max-requests",
            type=int,
            default=20,
            help="Maximum search pages to fetch this run",
        )
        parser.add_argument(
            "--circuit-breaker-cooldown",
            type=int,
            default=7200,
            help="Seconds to keep the circuit breaker open after a block",
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
        categories = self._select_categories(options["category"])

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

        scope = (
            "catalog"
            if options["category"] is None
            else f"category:{options['category']}"
        )
        budget = options["max_requests"]
        cooldown = options["circuit_breaker_cooldown"]

        state = self._load_state(scope)
        cat_index = state.category
        page = state.page

        updated = 0
        created = 0
        skipped = 0
        consumed = 0

        try:
            while cat_index < len(categories):
                if consumed >= budget:
                    break

                category, sub_category = categories[cat_index]
                response = client.search(
                    category, sub_category, page=page, sort="relevance"
                )
                consumed += 1

                for product in response.products:
                    result = self._process_product(product)
                    if result is None:
                        skipped += 1
                    elif result:
                        created += 1
                    else:
                        updated += 1

                if page + 1 < response.pagination.total_pages:
                    page += 1
                else:
                    cat_index += 1
                    page = 0

                self._save_state(scope, cat_index, page)
        except VmpBlockedError as exc:
            circuit_breaker.open(cooldown)
            self._save_state(scope, cat_index, page)
            raise CommandError(str(exc)) from exc

        if cat_index >= len(categories):
            self._reset_state(scope)
            self.stdout.write(self.style.SUCCESS("Catalog crawl cycle complete"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers, created {created} new beers, "
                f"skipped {skipped} without price! Pages {consumed}"
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

    def _load_state(self, scope: str) -> VmpCrawlState:
        with transaction.atomic():
            state, _ = VmpCrawlState.objects.select_for_update().get_or_create(
                scope=scope
            )
            if state.started is None:
                state.started = timezone.now()
                state.save()
            return state

    def _save_state(self, scope: str, category: int, page: int) -> None:
        VmpCrawlState.objects.filter(scope=scope).update(category=category, page=page)

    def _reset_state(self, scope: str) -> None:
        VmpCrawlState.objects.filter(scope=scope).update(
            category=0, page=0, started=None
        )

    def _process_product(self, product: VmpProduct) -> bool | None:
        code = int(product.code)
        try:
            beer = Beer.objects.get(vmp_id=code)
            is_new = False
        except Beer.DoesNotExist:
            beer = Beer(vmp_id=code)
            is_new = True

        if not self._save_beer(beer, product):
            return None
        return is_new

    def _save_beer(self, beer: Beer, product: VmpProduct) -> bool:
        if product.price is None:
            return False
        apply_product_fields(beer, product)
        beer.post_delivery = post_delivery(product)
        beer.store_delivery = store_delivery(product)
        beer.save()
        return True
