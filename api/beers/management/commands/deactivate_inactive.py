from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from beers.models import Beer, Stock
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("days", type=int, help="Number of days since last update")

    def handle(self, *args: Any, **options: Any) -> None:
        days = options["days"]

        inactive_beers = self._get_inactive_beers(days)
        deactivated_count = self._deactivate_beers(inactive_beers)
        unstocked_count = self._unstock_beers(inactive_beers)

        self.stdout.write(
            self.style.SUCCESS(
                f"Set {deactivated_count} beers inactive and unstocked {unstocked_count} beers"
            )
        )

    def _get_inactive_beers(self, days: int):
        time_threshold = timezone.now() - timedelta(days=days)
        return Beer.objects.filter(vmp_updated__lte=time_threshold, active=True)

    def _deactivate_beers(self, beers) -> int:
        updated_count = beers.update(active=False)
        return updated_count

    def _unstock_beers(self, beers) -> int:
        now = timezone.now()
        stocks = Stock.objects.filter(beer__in=beers)
        updated_count = stocks.update(quantity=0, unstocked_at=now)
        return updated_count
