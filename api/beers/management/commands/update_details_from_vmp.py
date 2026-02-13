from __future__ import annotations

from argparse import ArgumentParser

import cloudscraper25
from beers.models import Beer, ExternalAPI
from django.core.management.base import BaseCommand
from django.utils import timezone

CHARACTERISTIC_FIELDS = {
    "Fylde": "fullness",
    "Sødme": "sweetness",
    "Friskhet": "freshness",
    "Bitterhet": "bitterness",
}


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("calls", type=int, help="Number of beers to process")

    def handle(self, *args, **options) -> None:
        try:
            baseurl = ExternalAPI.objects.get(name="vinmonopolet_v3").baseurl
        except ExternalAPI.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("vinmonopolet_v3 external API configuration not found")
            )
            return

        url = f"{baseurl}products/"
        calls_limit = options["calls"]

        products_without_details = Beer.objects.filter(
            active=True, vmp_details_fetched=None
        )
        products = products_without_details[:calls_limit]

        if not products:
            self.stdout.write(
                self.style.WARNING("No products found that need detail updates")
            )
            return

        self.stdout.write(f"Processing {len(products)} products...")

        updated = 0
        failed = 0

        for product in products:
            if self._update_product_details(product, url):
                updated += 1
            else:
                failed += 1

        remaining = products_without_details.count() - len(products)
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers and failed to update {failed} beers. "
                f"{remaining} products still need details."
            )
        )

    def _update_product_details(self, product: Beer, url: str) -> bool:
        try:
            response = self._call_api(url, product.vmp_id)
            content = response.get("content", {})

            top_level_mapping = {
                "color": "color",
                "smell": "aroma",
                "taste": "taste",
                "allergens": "allergens",
                "method": "method",
            }

            for response_key, product_attr in top_level_mapping.items():
                if response_key in response:
                    setattr(product, product_attr, response[response_key])

            for char in content.get("characteristics", []):
                field = CHARACTERISTIC_FIELDS.get(char.get("name"))
                if field:
                    setattr(product, field, char["value"])

            storage = content.get("storagePotential")
            if storage:
                product.storable = storage.get("formattedValue", "")

            if "vintage" in response:
                product.year = response["vintage"]
            elif "year" in response:
                product.year = response["year"]

            if "sugar" in response:
                product.sugar = self._parse_sugar_value(response["sugar"])
            if "acid" in response:
                product.acid = self._parse_acid_value(response["acid"])

            ingredients = content.get("ingredients", [])
            if ingredients:
                product.raw_materials = ingredients[0].get("formattedValue", "")

            food_pairing = content.get("isGoodFor", [])
            if food_pairing:
                product.food_pairing = ", ".join(food["name"] for food in food_pairing)

            product.vmp_details_fetched = timezone.now()
            product.save()
            return True

        except Exception:
            return False

    def _call_api(self, url: str, product_id: int) -> dict:
        req_url = f"{url}{product_id}?fields=FULL"
        scraper = cloudscraper25.create_scraper(interpreter="nodejs")
        return scraper.get(req_url, headers={"Accept": "application/json"}).json()

    def _parse_sugar_value(self, sugar_str: str) -> float:
        return float(sugar_str.replace("<", "").replace(",", ".").split(" ")[-1])

    def _parse_acid_value(self, acid_str: str) -> float:
        return float(acid_str.replace(",", "."))
