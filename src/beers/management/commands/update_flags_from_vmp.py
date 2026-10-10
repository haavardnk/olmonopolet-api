from __future__ import annotations

from argparse import ArgumentParser

from django.core.management.base import CommandError
from django.db import transaction

from beers.management.commands._vmp import CATEGORIES, VmpCommand
from beers.models import Beer
from clients.vmp import VmpApiError, VmpBlockedError, VmpClient, circuit_breaker

FLAGS: dict[str, str] = {"vegan": "vegan", "newProducts": "is_new"}


class Command(VmpCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
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

        for facet, field in FLAGS.items():
            try:
                ids = self._flagged_ids(client, facet)
            except VmpBlockedError as exc:
                circuit_breaker.open(options["circuit_breaker_cooldown"])
                raise CommandError(str(exc)) from exc
            except VmpApiError as exc:
                raise CommandError(str(exc)) from exc

            with transaction.atomic():
                cleared = (
                    Beer.objects.filter(**{field: True})
                    .exclude(vmp_id__in=ids)
                    .update(**{field: False})
                )
                flagged = (
                    Beer.objects.filter(vmp_id__in=ids)
                    .exclude(**{field: True})
                    .update(**{field: True})
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"{field}: {len(ids)} on vinmonopolet, "
                    f"flagged {flagged}, cleared {cleared}"
                )
            )

    def _flagged_ids(self, client: VmpClient, facet: str) -> set[int]:
        ids: set[int] = set()
        for category, sub_category in CATEGORIES:
            page = 0
            total_pages = 1
            while page < total_pages:
                response = client.search(
                    category, sub_category, page=page, sort="relevance", flag=facet
                )
                if not any(crumb.facet_code == facet for crumb in response.breadcrumbs):
                    raise VmpApiError(f"vinmonopolet ignored the '{facet}' facet")
                ids.update(int(product.code) for product in response.products)
                total_pages = response.pagination.total_pages
                page += 1
        return ids
