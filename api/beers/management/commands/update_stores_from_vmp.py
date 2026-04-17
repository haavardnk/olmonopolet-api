from __future__ import annotations

from typing import Any

import cloudscraper25
from beers.models import ExternalAPI, Store
from cloudscraper25 import CloudScraper
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options) -> None:
        try:
            baseurl = ExternalAPI.objects.get(name="vinmonopolet").baseurl
        except ExternalAPI.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("vinmonopolet external API configuration not found")
            )
            return

        updated = 0
        created = 0

        scraper = cloudscraper25.create_scraper(
            interpreter="nodejs",
            browser="chrome",
            enable_stealth=True,
        )
        stores_data = self._fetch_stores_list(baseurl, scraper)

        self.stdout.write(f"Processing {len(stores_data)} stores...")

        for store_data in stores_data:
            result = self._process_store(baseurl, scraper, store_data)
            if result == "updated":
                updated += 1
            elif result == "created":
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated: {updated}, Created: {created}."
            )
        )

    def _process_store(
        self, baseurl: str, scraper: CloudScraper, store_data: dict[str, Any]
    ) -> str:
        store_code = store_data["code"]
        store_details = self._fetch_store_details(baseurl, scraper, store_code)

        try:
            store = Store.objects.get(store_id=store_code)
            self._update_existing_store(store, store_details)
            return "updated"

        except Store.DoesNotExist:
            self._create_new_store(store_code, store_details)
            return "created"

    def _fetch_stores_list(
        self, baseurl: str, scraper: CloudScraper
    ) -> list[dict[str, Any]]:
        url = f"{baseurl}products/search?currentPage=0&fields=FULL&pageSize=1&q="
        response = scraper.get(url, headers={"Accept": "application/json"}).json()

        for facet in response.get("facets", []):
            if facet.get("code") == "availableInStores":
                return facet.get("values", [])

        raise ValueError("No 'availableInStores' facet found in API response")

    def _fetch_store_details(
        self, baseurl: str, scraper: CloudScraper, store_code: str
    ) -> dict[str, Any]:
        detail_url = f"{baseurl}stores/{store_code}"
        return scraper.get(
            detail_url, headers={"Accept": "application/json"}
        ).json()

    def _update_existing_store(
        self, store: Store, store_details: dict[str, Any]
    ) -> None:
        store.name = store_details["displayName"]
        store.address = store_details["address"]["line1"]
        store.zipcode = store_details["address"]["postalCode"]
        store.area = store_details["address"]["town"]
        store.category = store_details["assortment"]
        store.gps_lat = store_details["geoPoint"]["latitude"]
        store.gps_long = store_details["geoPoint"]["longitude"]
        store.save()

    def _create_new_store(self, store_code: str, store_details: dict[str, Any]) -> None:
        Store.objects.create(
            store_id=store_code,
            name=store_details["displayName"],
            address=store_details["address"]["line1"],
            zipcode=store_details["address"]["postalCode"],
            area=store_details["address"]["town"],
            category=store_details["assortment"],
            gps_lat=store_details["geoPoint"]["latitude"],
            gps_long=store_details["geoPoint"]["longitude"],
        )
