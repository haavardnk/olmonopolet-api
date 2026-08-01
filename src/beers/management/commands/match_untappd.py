from __future__ import annotations

import time
from argparse import ArgumentParser

from django.core.management.base import BaseCommand
from django.db import DatabaseError
from fuzzywuzzy import fuzz, process

from beers.models import Beer
from clients.untappd import (
    UntappdClient,
    UntappdSearchResult,
    generate_query_variations,
)


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("calls", type=int, help="Number of beers to process")

    def handle(self, *args, **options) -> None:
        beers = Beer.objects.filter(
            untpd_id__isnull=True, match_manually=False, active=True
        )

        calls_limit = options["calls"]
        matched = 0
        failed = 0
        failed_beers: list[Beer] = []

        self.stdout.write(f"Processing {min(calls_limit, beers.count())} beers...")

        client = UntappdClient()

        for beer in beers[:calls_limit]:
            time.sleep(1)

            is_matched, match_title = self._process_beer(beer, client)
            if is_matched:
                matched += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Matched {beer} as {match_title}")
                )
            else:
                failed += 1
                failed_beers.append(beer)
                if match_title:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Failed to match {beer}... Possible option: {match_title}"
                        )
                    )
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to match {beer}..."))

        self.stdout.write(self.style.SUCCESS(f"Matched: {matched} Failed: {failed}"))

    def _process_beer(
        self, beer: Beer, client: UntappdClient
    ) -> tuple[bool, str | None]:
        result, score = self._find_beer_match(beer.vmp_name, client)

        try:
            if score and score > 40 and result:
                beer.untpd_id = result.untpd_id
                beer.untpd_url = result.url
                beer.save()
                return True, result.name
            else:
                self._mark_as_failed(beer)
                return False, result.name if result else None

        except (DatabaseError, ValueError):
            self._mark_as_failed(beer)
            return False, None

    def _find_beer_match(
        self, beer_name: str, client: UntappdClient
    ) -> tuple[UntappdSearchResult | None, int | None]:
        for query in generate_query_variations(beer_name):
            self.stdout.write(f"Trying query: {query}")

            results = client.search_beers(query)
            if not results:
                continue

            best_match = process.extractOne(
                beer_name, [result.name for result in results], scorer=fuzz.ratio
            )
            if not best_match:
                continue

            for result in results:
                if result.name == best_match[0]:
                    return result, best_match[1]

        self.stdout.write("No match found.")
        return None, None

    def _mark_as_failed(self, beer: Beer) -> None:
        beer.description = "Missing on Untappd."
        beer.match_manually = True
        beer.save()
