from __future__ import annotations

import json
import re
from argparse import ArgumentParser
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import requests
from beers.api.utils import sync_unmatched_checkins
from beers.models import UntappdCheckin, UntappdRssFeed
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync Untappd RSS feeds to import new checkins"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--user", type=str, default=None, help="Sync only this username"
        )

    def handle(self, *args, **options) -> None:
        feeds = UntappdRssFeed.objects.filter(active=True).select_related("user")
        if options["user"]:
            feeds = feeds.filter(user__username=options["user"])

        if not feeds.exists():
            self.stdout.write("No active RSS feeds found")
            return

        scraper = requests.Session()
        scraper.headers.update({"User-Agent": "Mozilla/5.0"})
        total_imported = 0

        for feed_obj in feeds:
            count = self._process_feed(feed_obj, scraper)
            total_imported += count

        result = sync_unmatched_checkins()
        summary = {
            "imported": total_imported,
            "synced": result["synced_count"],
            "users_affected": result["users_affected"],
        }
        self.stdout.write(json.dumps(summary))

    def _process_feed(self, feed_obj: UntappdRssFeed, scraper: requests.Session) -> int:
        self.stdout.write(f"Processing feed for {feed_obj.user.username}")

        parsed = feedparser.parse(feed_obj.feed_url)
        if parsed.bozo and not parsed.entries:
            self.stdout.write(
                self.style.ERROR(f"Failed to parse feed for {feed_obj.user.username}")
            )
            return 0

        new_entries = self._filter_new_entries(parsed.entries)
        if not new_entries:
            self.stdout.write(f"No new entries for {feed_obj.user.username}")
            return 0

        self.stdout.write(
            f"Found {len(new_entries)} new entries for {feed_obj.user.username}"
        )

        imported = 0

        for entry in new_entries:
            checkin_url = entry.get("link", "")
            checkin_id = self._extract_checkin_id(checkin_url)
            if not checkin_id:
                continue

            pub_date = self._parse_pub_date(entry)
            title = entry.get("title", "")

            beer_id, rating = self._scrape_checkin_page(
                checkin_id, checkin_url, scraper
            )
            if beer_id:
                self.stdout.write(f"  {title} -> {beer_id} (rating: {rating})")
                self._save_checkin(
                    feed_obj.user, int(checkin_id), beer_id, rating, pub_date
                )
                imported += 1
            else:
                self.stdout.write(self.style.WARNING(f"  No match: {title}"))

        if imported > 0:
            feed_obj.last_synced = datetime.now(timezone.utc)
            feed_obj.save(update_fields=["last_synced"])

        self.stdout.write(
            f"Imported {imported} checkins for {feed_obj.user.username}"
        )
        return imported

    def _filter_new_entries(self, entries: list) -> list:
        checkin_ids: list[int] = []
        entry_map: dict[int, dict] = {}
        for entry in entries:
            cid = self._extract_checkin_id(entry.get("link", ""))
            if cid:
                int_cid = int(cid)
                checkin_ids.append(int_cid)
                entry_map[int_cid] = entry

        existing = set(
            UntappdCheckin.objects.filter(untpd_checkin_id__in=checkin_ids)
            .values_list("untpd_checkin_id", flat=True)
        )
        return [entry_map[cid] for cid in checkin_ids if cid not in existing]

    def _extract_checkin_id(self, link: str) -> str | None:
        match = re.search(r"/checkin/(\d+)", link)
        return match.group(1) if match else None

    def _parse_pub_date(self, entry: dict) -> datetime | None:
        published_parsed = entry.get("published_parsed")
        if not published_parsed:
            return None
        try:
            ts = timegm(published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError):
            return None

    def _scrape_checkin_page(
        self, checkin_id: str, checkin_url: str, scraper: requests.Session
    ) -> tuple[int | None, float | None]:
        try:
            response = scraper.get(checkin_url, timeout=15)
            if response.status_code != 200:
                self.stdout.write(
                    self.style.ERROR(
                        f"  HTTP {response.status_code} for checkin {checkin_id}"
                    )
                )
                return None, None
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error fetching checkin {checkin_id}: {e}")
            )
            return None, None

        return self._extract_beer_id(soup), self._extract_rating(soup)

    def _extract_beer_id(self, soup: BeautifulSoup) -> int | None:
        try:
            beer_link = soup.find("a", {"class": "label"})
            if beer_link and beer_link.get("href"):
                href = str(beer_link["href"])
                match = re.search(r"/beer/[^/]+/(\d+)", href)
                if match:
                    return int(match.group(1))
                parts = href.rstrip("/").split("/")
                if parts:
                    return int(parts[-1])
        except (ValueError, IndexError, AttributeError):
            pass

        try:
            og_url = soup.find("meta", {"property": "og:url"})
            if og_url and og_url.get("content"):
                content = str(og_url["content"])
                if "/beer/" in content:
                    match = re.search(r"/beer/[^/]+/(\d+)", content)
                    if match:
                        return int(match.group(1))
        except (ValueError, AttributeError):
            pass

        try:
            beer_name_link = soup.select_one("p.beer-name a")
            if beer_name_link and beer_name_link.get("href"):
                href = str(beer_name_link["href"])
                parts = href.rstrip("/").split("/")
                if parts:
                    return int(parts[-1])
        except (ValueError, IndexError, AttributeError):
            pass

        return None

    def _extract_rating(self, soup: BeautifulSoup) -> float | None:
        try:
            caps_elem = soup.find("div", {"class": "caps"})
            if caps_elem and caps_elem.get("data-rating"):
                val = float(str(caps_elem["data-rating"]))
                if val > 0:
                    return val
        except (ValueError, AttributeError):
            pass

        try:
            rating_elem = soup.select_one("span.rating")
            if rating_elem:
                match = re.search(r"[\d.]+", rating_elem.text)
                if match:
                    val = float(match.group())
                    if val > 0:
                        return val
        except (ValueError, AttributeError):
            pass

        return None

    def _save_checkin(
        self,
        user,
        checkin_id: int,
        beer_id: int,
        rating: float | None,
        checkin_at: datetime | None,
    ) -> None:
        UntappdCheckin.objects.get_or_create(
            untpd_checkin_id=checkin_id,
            defaults={
                "user": user,
                "untpd_beer_id": beer_id,
                "rating": rating,
                "checkin_at": checkin_at,
            },
        )
