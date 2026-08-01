from __future__ import annotations

from argparse import ArgumentParser
from itertools import chain

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from beers.models import Brewery
from clients.untappd import UntappdBrewery, UntappdClient


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("calls", type=int, help="Number of breweries to process")

    def handle(self, *args, **options) -> None:
        breweries = self._get_prioritized_breweries()
        client = UntappdClient()
        updated = 0
        attempted = 0

        for brewery in breweries[: options["calls"]]:
            attempted += 1
            if self._update_brewery_from_untappd(brewery, client):
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Updated {updated} breweries out of {options['calls']}")
        )

        if attempted and updated == 0:
            raise CommandError(
                f"All {attempted} brewery updates failed (untappd unreachable)"
            )

    def _get_prioritized_breweries(self) -> list[Brewery]:
        breweries1 = Brewery.objects.filter(label_url__isnull=True)
        breweries2 = Brewery.objects.all().order_by(
            F("untpd_updated").asc(nulls_first=True)
        )

        seen_ids = set()
        breweries: list[Brewery] = []
        for brewery in chain(breweries1, breweries2):
            if brewery.pk not in seen_ids:
                seen_ids.add(brewery.pk)
                breweries.append(brewery)

        return breweries

    def _update_brewery_from_untappd(
        self, brewery: Brewery, client: UntappdClient
    ) -> bool:
        url = brewery.untpd_url
        self.stdout.write(f"{brewery.id} {url}")

        data = client.get_brewery(url)
        if data is None:
            self.stdout.write(self.style.ERROR(f"Error fetching {url}"))
            return False

        self._apply_fields(brewery, data)
        brewery.untpd_updated = timezone.now()
        brewery.save()
        return True

    def _apply_fields(self, brewery: Brewery, data: UntappdBrewery) -> None:
        if data.name:
            brewery.name = data.name
        if data.description:
            brewery.description = data.description
        if data.label_url:
            brewery.label_url = data.label_url
