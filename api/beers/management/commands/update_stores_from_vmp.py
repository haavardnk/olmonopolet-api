from __future__ import annotations

from typing import Any

import cloudscraper25
import xmltodict
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
        failed = 0

        scraper = cloudscraper25.create_scraper(interpreter="nodejs")
        stores_data = self._fetch_stores_list(baseurl, scraper)

        if not stores_data:
            self.stdout.write(self.style.ERROR("Failed to fetch stores list from API"))
            return

        self.stdout.write(f"Processing {len(stores_data)} stores...")

        for store_data in stores_data:
            result = self._process_store(baseurl, scraper, store_data)
            if result == "updated":
                updated += 1
            elif result == "created":
                created += 1
            else:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated: {updated}, Created: {created}, Failed: {failed}."
            )
        )

    def _process_store(
        self, baseurl: str, scraper: CloudScraper, store_data: dict[str, Any]
    ) -> str:
        store_code = store_data["code"]

        store_details = self._fetch_store_details(baseurl, scraper, store_code)
        if not store_details:
            return "failed"

        try:
            try:
                store = Store.objects.get(store_id=store_code)
                self._update_existing_store(store, store_details)
                return "updated"

            except Store.DoesNotExist:
                self._create_new_store(store_code, store_details)
                return "created"

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error processing store {store_code}: {e}")
            )
            return "failed"

    def _fetch_stores_list(
        self, baseurl: str, scraper: CloudScraper
    ) -> list[dict[str, Any]] | None:
        url = f"{baseurl}products/search/?currentPage=0&fields=FULL&pageSize=1&query="

        try:
            response_text = scraper.get(url).text
            response = xmltodict.parse(response_text)
            return response["productCategorySearchPage"]["facets"][0]["values"]
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching stores list: {e}"))
            return None

    def _fetch_store_details(
        self, baseurl: str, scraper: CloudScraper, store_code: str
    ) -> dict[str, Any] | None:
        detail_url = f"{baseurl}stores/{store_code}"

        try:
            detail_response_text = scraper.get(detail_url).text
            detail_response = xmltodict.parse(detail_response_text)
            return detail_response["pointOfService"]
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error fetching store details for {store_code}: {e}")
            )
            return None

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
