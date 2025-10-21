from __future__ import annotations

import time
from argparse import ArgumentParser

import cloudscraper25
from beers.models import Beer
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from fuzzywuzzy import fuzz, process


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

        for beer in beers[:calls_limit]:
            time.sleep(1)

            is_matched, match_title = self._process_beer(beer)
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

    def _process_beer(self, beer: Beer) -> tuple[bool, str | None]:
        result, score = self._find_beer_match(beer.vmp_name)

        try:
            if score and score > 40 and result:
                beer.untpd_id = int(result[1])
                beer.untpd_url = result[2]
                beer.save()
                return True, result[0]
            else:
                self._mark_as_failed(beer)
                match_title = result[0] if result else None
                return False, match_title

        except Exception:
            self._mark_as_failed(beer)
            return False, None

    def _find_beer_match(
        self, beer_name: str
    ) -> tuple[tuple[str, str, str] | None, int | None]:
        queries = self._generate_query_variations(beer_name)

        for query in queries:
            self.stdout.write(f"Trying query: {query}")

            html = self._query_untappd(query)
            if html:
                results = self._parse_search_results(html)

                beer_names = [result[0] for result in results]

                best_match = process.extractOne(
                    beer_name, beer_names, scorer=fuzz.ratio
                )

                if best_match:
                    matched_name = best_match[0]
                    similarity_score = best_match[1]

                    for result in results:
                        if result[0] == matched_name:
                            return result, similarity_score

        self.stdout.write("No match found.")
        return None, None

    def _generate_query_variations(self, beer_name: str) -> list[str]:
        variations = [beer_name]

        if " x " in beer_name:
            main_brewery, rest = beer_name.split(" x ", 1)
            collab_removed = main_brewery.strip() + " " + rest.strip()
            variations.append(collab_removed)
        else:
            collab_removed = beer_name

        words = collab_removed.split()
        for i in range(len(words) - 1, 2, -1):
            variations.append(" ".join(words[:i]))

        return variations

    def _query_untappd(self, query: str) -> str | None:
        scraper = cloudscraper25.create_scraper()
        url = f"https://untappd.com/search?q={query}"

        response = scraper.get(url)

        if response.status_code == 200:
            return response.text
        else:
            self.stdout.write(
                self.style.ERROR(f"Failed to fetch results for query: {query}")
            )
            return None

    def _parse_search_results(self, html: str) -> list[tuple[str, str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for beer_item in soup.select(".beer-item"):
            name_element = beer_item.select_one(".name")
            link_element = beer_item.select_one("a")

            if name_element and link_element and link_element.get("href"):
                beer_name = name_element.text.strip()
                beer_link = str(link_element["href"])
                untappd_id = beer_link.split("/")[-1]
                full_url = f"https://untappd.com{beer_link}"

                results.append((beer_name, untappd_id, full_url))

        return results

    def _mark_as_failed(self, beer: Beer) -> None:
        beer.description = "Missing on Untappd."
        beer.match_manually = True
        beer.save()
