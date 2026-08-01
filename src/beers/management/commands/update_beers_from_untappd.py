from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from itertools import chain

from clients.untappd import UntappdBeer, UntappdClient
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from beers.models import Beer, Brewery


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("calls", type=int, help="Number of beers to process")

    def handle(self, *args, **options) -> None:
        beers = self._get_prioritized_beers()
        client = UntappdClient()
        updated = 0
        attempted = 0

        for beer in beers[: options["calls"]]:
            attempted += 1
            if self._update_beer_from_untappd(beer, client):
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Updated {updated} beers out of {options['calls']}")
        )

        if attempted and updated == 0:
            raise CommandError(
                f"All {attempted} untappd updates failed (untappd unreachable)"
            )

    def _get_prioritized_beers(self) -> list[Beer]:
        beers1 = Beer.objects.filter(
            untpd_id__isnull=False, prioritize_recheck=True, active=True
        )
        beers2 = Beer.objects.filter(
            untpd_id__isnull=False, rating__isnull=True, active=True
        )
        beers3 = Beer.objects.filter(
            untpd_updated__lte=timezone.now() - timedelta(days=7),
            untpd_id__isnull=False,
            active=True,
            checkins__lte=500,
        )
        beers4 = Beer.objects.filter(untpd_id__isnull=False, active=True).order_by(
            "untpd_updated"
        )

        seen_ids = set()
        beers: list[Beer] = []
        for beer in chain(beers1, beers2, beers3, beers4):
            if beer.pk not in seen_ids:
                seen_ids.add(beer.pk)
                beers.append(beer)

        return beers

    def _update_beer_from_untappd(self, beer: Beer, client: UntappdClient) -> bool:
        url = beer.untpd_url
        if not url:
            self.stdout.write(self.style.ERROR(f"No URL for beer: {beer.vmp_name}"))
            return False

        self.stdout.write(f"{beer.vmp_name} {url}")

        data = client.get_beer(url)
        if data is None:
            self.stdout.write(self.style.ERROR(f"Error fetching {url}"))
            return False

        self._apply_fields(beer, data)
        beer.untpd_updated = timezone.now()
        beer.prioritize_recheck = False
        beer.save()
        return True

    def _apply_fields(self, beer: Beer, data: UntappdBeer) -> None:
        beer.untpd_id = data.untpd_id or beer.untpd_id
        beer.untpd_name = data.name or beer.untpd_name
        beer.untpd_url = data.untpd_url or beer.untpd_url
        beer.description = data.description or beer.description
        beer.ibu = data.ibu
        if data.rating is not None:
            beer.rating = data.rating
        if data.checkins is not None:
            beer.checkins = data.checkins
        if data.style is not None:
            beer.style = data.style
        if data.abv is not None:
            beer.abv = data.abv
        if data.label_hd_url:
            beer.label_hd_url = data.label_hd_url
        if data.label_sm_url:
            beer.label_sm_url = data.label_sm_url
        self._link_brewery(beer, data)

    def _link_brewery(self, beer: Beer, data: UntappdBeer) -> None:
        if not data.brewery_url:
            return
        brewery, _ = Brewery.objects.get_or_create(
            untpd_url=data.brewery_url,
            defaults={"name": data.brewery_name},
        )
        beer.brewery = brewery
