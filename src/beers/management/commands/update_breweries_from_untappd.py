from __future__ import annotations

import json
from argparse import ArgumentParser
from itertools import chain

import cloudscraper25
from beers.models import Brewery
from bs4 import BeautifulSoup
from cloudscraper25 import CloudScraper
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("calls", type=int, help="Number of breweries to process")

    def handle(self, *args, **options) -> None:
        breweries = self._get_prioritized_breweries()
        scraper = cloudscraper25.create_scraper()
        updated = 0
        attempted = 0

        for brewery in breweries[: options["calls"]]:
            attempted += 1
            if self._update_brewery_from_untappd(brewery, scraper):
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
        self, brewery: Brewery, scraper: CloudScraper
    ) -> bool:
        url = self._brewery_url(brewery)
        self.stdout.write(f"{brewery.id} {url}")

        try:
            response = scraper.get(
                url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30
            )
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching {url}: {e}"))
            return False

        self._update_brewery_fields(brewery, soup)
        brewery.untpd_updated = timezone.now()
        brewery.save()
        return True

    def _brewery_url(self, brewery: Brewery) -> str:
        return brewery.untpd_url

    def _extract_brewery_ld(self, soup: BeautifulSoup) -> dict | None:
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "Brewery":
                return data
        return None

    def _update_brewery_fields(self, brewery: Brewery, soup: BeautifulSoup) -> None:
        data = self._extract_brewery_ld(soup)
        if data:
            name = data.get("name")
            if name:
                brewery.name = name
            description = data.get("description")
            if description:
                brewery.description = description
            image = self._extract_ld_image(data.get("image"))
            if image:
                brewery.label_url = self._normalize_url(image)

        if not brewery.label_url:
            logo = self._extract_logo(soup)
            if logo:
                brewery.label_url = logo

    def _extract_ld_image(self, image: object) -> str | None:
        if isinstance(image, dict):
            return image.get("contentUrl") or image.get("url")
        if isinstance(image, str):
            return image
        return None

    def _extract_logo(self, soup: BeautifulSoup) -> str | None:
        label_elem = soup.find("a", {"class": "label image-big"})
        if label_elem:
            data_image = label_elem.get("data-image")
            if data_image:
                return self._normalize_url(str(data_image))
        return None

    def _normalize_url(self, url: str) -> str:
        return (
            url.replace("://", "PLACEHOLDER")
            .replace("//", "/")
            .replace("PLACEHOLDER", "://")
        )
