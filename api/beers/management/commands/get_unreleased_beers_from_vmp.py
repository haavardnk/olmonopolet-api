from __future__ import annotations

from typing import Any

import cloudscraper25
import xmltodict
from beers.models import Beer, ExternalAPI, VmpNotReleased
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    def handle(self, *args, **options) -> None:
        try:
            baseurl = ExternalAPI.objects.get(name="vinmonopolet_v3").baseurl
        except ExternalAPI.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("vinmonopolet_v3 external API configuration not found")
            )
            return

        updated = 0
        created = 0

        products = VmpNotReleased.objects.all()

        if not products.exists():
            self.stdout.write(self.style.WARNING("No unreleased products found"))
            return

        self.stdout.write(f"Processing {products.count()} unreleased products...")

        for product in products:
            was_updated, was_created = self._process_product(product, baseurl)
            if was_updated:
                updated += 1
            elif was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers and created {created} new beers!"
            )
        )

    def _process_product(
        self, product: VmpNotReleased, baseurl: str
    ) -> tuple[bool, bool]:
        url = f"{baseurl}products/{product.id}"

        try:
            response = self._call_api(url)["product"]

            try:
                beer = Beer.objects.get(vmp_id=int(response["code"]))
                self._update_existing_beer(beer, response)
                product.delete()
                return True, False

            except Beer.DoesNotExist:
                self._create_new_beer(response)
                product.delete()
                return False, True

        except Exception:
            return False, False

    def _update_existing_beer(self, beer: Beer, response: dict[str, Any]) -> None:
        beer.vmp_name = response["name"]
        beer.main_category = response["main_category"]["name"]

        if "main_sub_category" in response:
            beer.sub_category = response["main_sub_category"]["name"]

        beer.country = response["main_country"]["name"]
        beer.volume = float(response["volume"]["value"]) / 100.0

        if "price" in response:
            price_value = response["price"]["value"]
            volume_value = float(response["volume"]["value"])
            beer.price = price_value
            beer.price_per_volume = self._calculate_price_per_volume(
                price_value, volume_value
            )

        beer.product_selection = response["product_selection"]
        beer.vmp_url = f"https://www.vinmonopolet.no{response['url']}"
        beer.vmp_updated = timezone.now()

        if not beer.active:
            beer.active = True

        beer.save()

    def _create_new_beer(self, response: dict[str, Any]) -> Beer:
        volume_value = float(response["volume"]["value"])

        beer_data = {
            "vmp_id": int(response["code"]),
            "vmp_name": response["name"],
            "main_category": response["main_category"]["name"],
            "country": response["main_country"]["name"],
            "volume": volume_value / 100.0,
            "product_selection": response["product_selection"],
            "vmp_url": f"https://www.vinmonopolet.no{response['url']}",
            "vmp_updated": timezone.now(),
        }

        beer = Beer.objects.create(**beer_data)
        if "main_sub_category" in response:
            beer.sub_category = response["main_sub_category"]["name"]

        if "price" in response:
            price_value = response["price"]["value"]
            beer.price = price_value
            beer.price_per_volume = self._calculate_price_per_volume(
                price_value, volume_value
            )

        beer.save()
        return beer

    def _call_api(self, url: str) -> dict[str, Any]:
        scraper = cloudscraper25.create_scraper(interpreter="nodejs")
        response_text = scraper.get(url, timeout=30).text
        return xmltodict.parse(response_text)

    def _calculate_price_per_volume(self, price: float, volume_value: float) -> float:
        volume_in_liters = volume_value / 100.0
        return price / volume_in_liters
