from __future__ import annotations

from argparse import ArgumentParser

import cloudscraper25
import xmltodict
from beers.models import Beer, ExternalAPI
from django.core.management.base import BaseCommand
from django.utils import timezone


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

            mapping = {
                "fullness": "fullness",
                "sweetness": "sweetness",
                "freshness": "freshness",
                "bitterness": "bitterness",
                "color": "color",
                "smell": "aroma",
                "taste": "taste",
                "matured": "storable",
                "allergens": "allergens",
                "method": "method",
            }

            for response_key, product_attr in mapping.items():
                if response_key in response:
                    setattr(product, product_attr, response[response_key])

            if "vintage" in response:
                product.year = response["vintage"]
            elif "year" in response:
                product.year = response["year"]

            if "sugar" in response:
                product.sugar = self._parse_sugar_value(response["sugar"])
            if "acid" in response:
                product.acid = self._parse_acid_value(response["acid"])

            if "raastoff" in response and "name" in response["raastoff"]:
                product.raw_materials = response["raastoff"]["name"]
            if "isGoodFor" in response:
                product.food_pairing = self._parse_food_pairing(response["isGoodFor"])

            product.vmp_details_fetched = timezone.now()
            product.save()
            return True

        except Exception:
            return False

    def _call_api(self, url: str, product_id: int) -> dict:
        req_url = f"{url}{product_id}?fields=FULL"
        scraper = cloudscraper25.create_scraper(interpreter="nodejs")
        response_text = scraper.get(req_url).text
        return xmltodict.parse(response_text)["product"]

    def _parse_sugar_value(self, sugar_str: str) -> float:
        return float(sugar_str.replace("<", "").replace(",", ".").split(" ")[-1])

    def _parse_acid_value(self, acid_str: str) -> float:
        return float(acid_str.replace(",", "."))

    def _parse_food_pairing(self, food_data) -> str:
        if not isinstance(food_data, list):
            return food_data["name"]
        return ", ".join(food["name"] for food in food_data)
