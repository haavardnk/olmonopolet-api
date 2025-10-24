from __future__ import annotations

import json
import re
from argparse import ArgumentParser
from datetime import timedelta
from itertools import chain

import cloudscraper25
from beers.models import Beer
from bs4 import BeautifulSoup
from cloudscraper25 import CloudScraper
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("calls", type=int, help="Number of beers to process")

    def handle(self, *args, **options) -> None:
        beers = self._get_prioritized_beers()
        scraper = cloudscraper25.create_scraper()
        updated = 0

        for beer in beers[: options["calls"]]:
            if self._update_beer_from_untappd(beer, scraper):
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Updated {updated} beers out of {options['calls']}")
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

    def _update_beer_from_untappd(self, beer: Beer, scraper: CloudScraper) -> bool:
        url = beer.untpd_url
        if not url:
            self.stdout.write(self.style.ERROR(f"No URL for beer: {beer.vmp_name}"))
            return False

        self.stdout.write(f"{beer.vmp_name} {url}")

        try:
            response = scraper.get(
                url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30
            )
            soup = BeautifulSoup(response.text, "html.parser")
            json_ld_data = self._extract_json_ld_data(soup)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching {url}: {e}"))
            return False

        # Update beer data
        self._update_beer_fields(beer, soup, json_ld_data)
        beer.untpd_updated = timezone.now()
        beer.prioritize_recheck = False

        if beer.volume and beer.abv:
            beer.alcohol_units = (beer.volume * 1000 * beer.abv / 100 * 0.8) / 12

        beer.save()
        return True

    def _extract_json_ld_data(self, soup: BeautifulSoup) -> list[dict]:
        try:
            scripts = soup.find_all("script", type="application/ld+json")
            return [json.loads(script.string) for script in scripts if script.string]
        except (json.JSONDecodeError, AttributeError):
            return []

    def _update_beer_fields(
        self, beer: Beer, soup: BeautifulSoup, json_ld_data: list[dict]
    ) -> None:
        if json_ld_data:
            data = json_ld_data[0]
            beer.untpd_id = data.get("sku", beer.untpd_id)
            beer.untpd_name = data.get("name", beer.untpd_name)
            beer.brewery = data.get("brand", {}).get("name", beer.brewery)
            beer.rating = data.get("aggregateRating", {}).get(
                "ratingValue", beer.rating
            )
            beer.checkins = data.get("aggregateRating", {}).get(
                "reviewCount", beer.checkins
            )
            beer.description = data.get("description", beer.description)
        else:
            self._update_from_html_fallback(beer, soup)

        self._extract_html_only_fields(beer, soup)

    def _update_from_html_fallback(self, beer: Beer, soup: BeautifulSoup) -> None:
        try:
            og_url = soup.find("meta", {"property": "og:url"})
            if og_url and og_url.get("content"):
                content = str(og_url["content"])
                beer.untpd_id = int(content.split("/")[-1])
        except (AttributeError, ValueError, IndexError):
            pass

        try:
            brewery_elem = soup.find("p", {"class": "brewery"})
            name_elem = soup.find("div", {"class": "name"})
            if brewery_elem and name_elem:
                brewery_link = brewery_elem.find("a")
                name_header = name_elem.find("h1")
                brewery_text = brewery_link.text if brewery_link else ""
                name_text = name_header.text if name_header else ""
                beer.untpd_name = f"{brewery_text} {name_text}".strip()
                beer.brewery = brewery_text
        except AttributeError:
            pass

        try:
            caps_elem = soup.find("div", {"class": "caps"})
            if caps_elem and caps_elem.get("data-rating"):
                rating_value = str(caps_elem["data-rating"])
                beer.rating = float(rating_value)
        except (AttributeError, ValueError):
            pass

        try:
            raters_elem = soup.find("p", {"class": "raters"})
            if raters_elem:
                checkins_match = re.findall(r"\b\d+\b", raters_elem.text)
                if checkins_match:
                    beer.checkins = int(checkins_match[0])
        except (AttributeError, ValueError, IndexError):
            pass

        try:
            desc_elem = soup.find("div", {"class": "beer-descrption-read-less"})
            if desc_elem:
                beer.description = desc_elem.text.strip()
        except AttributeError:
            pass

    def _extract_html_only_fields(self, beer: Beer, soup: BeautifulSoup) -> None:
        try:
            style_elem = soup.find("p", {"class": "style"})
            if style_elem:
                beer.style = style_elem.text.strip()
        except AttributeError:
            pass

        try:
            abv_elem = soup.find("p", {"class": "abv"})
            if abv_elem:
                abv_numbers = re.findall(r"\d+\.?\d*", abv_elem.text)
                beer.abv = float(abv_numbers[0]) if abv_numbers else 0
        except (AttributeError, ValueError, IndexError):
            beer.abv = 0

        try:
            ibu_elem = soup.find("p", {"class": "ibu"})
            if ibu_elem:
                ibu_numbers = re.findall(r"\b\d+\b", ibu_elem.text)
                beer.ibu = int(ibu_numbers[0]) if ibu_numbers else None
        except (AttributeError, ValueError, IndexError):
            beer.ibu = None

        try:
            label_elem = soup.find("a", {"class": "label image-big"})
            if label_elem:
                data_image = label_elem.get("data-image")
                if data_image:
                    beer.label_hd_url = (
                        str(data_image)
                        .replace("://", "PLACEHOLDER")
                        .replace("//", "/")
                        .replace("PLACEHOLDER", "://")
                    )
                img_elem = label_elem.find("img")
                if img_elem:
                    src = img_elem.get("src")
                    if src:
                        beer.label_sm_url = str(src)
        except AttributeError:
            pass

        try:
            og_url_elem = soup.find("meta", {"property": "og:url"})
            if og_url_elem:
                content = og_url_elem.get("content")
                if content:
                    beer.untpd_url = str(content)
        except AttributeError:
            pass
