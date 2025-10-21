from __future__ import annotations

import cloudscraper25
import xmltodict
from beers.api.utils import parse_bool
from beers.models import Beer, ExternalAPI
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    def handle(self, *args, **options) -> None:
        try:
            baseurl = ExternalAPI.objects.get(name="vinmonopolet").baseurl
        except ExternalAPI.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("vinmonopolet external API configuration not found")
            )
            return

        url = f"{baseurl}products/search/"
        updated = 0
        created = 0

        products = [
            "øl",
            "sider",
            "mjød",
            "alkoholfritt_alkoholfritt_øl",
            "alkoholfritt_alkoholfri_ingefærøl",
            "alkoholfritt_alkoholfri_sider",
        ]

        for product in products:
            self.stdout.write(f"Processing product category: {product}")
            product_updated, product_created = self._process_product_category(
                url, product
            )
            updated += product_updated
            created += product_created

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers and created {created} new beers!"
            )
        )

    def _process_product_category(self, url: str, product: str) -> tuple[int, int]:
        updated = 0
        created = 0

        try:
            response, total_pages = self._call_api(url, 0, product)

            for page in range(total_pages):
                try:
                    response, _ = self._call_api(url, page, product)

                    for beer_data in response.get("products", []):
                        try:
                            beer = Beer.objects.get(vmp_id=int(beer_data["code"]))
                            self._update_existing_beer(beer, beer_data)
                            updated += 1

                        except Beer.DoesNotExist:
                            self._create_new_beer(beer_data)
                            created += 1

                except Exception:
                    continue

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error processing product category {product}: {e}")
            )

        return updated, created

    def _call_api(self, url: str, page: int, product: str) -> tuple[dict, int]:
        if "alkoholfritt" in product:
            query = f":relevance:visibleInSearch:true:mainCategory:alkoholfritt:mainSubCategory:{product}:"
        else:
            query = f":relevance:visibleInSearch:true:mainCategory:{product}:"

        req_url = f"{url}?currentPage={page}&fields=FULL&pageSize=100&query={query}"

        scraper = cloudscraper25.create_scraper(interpreter="nodejs")
        response_text = scraper.get(req_url).text
        response = xmltodict.parse(response_text)["productCategorySearchPage"]
        total_pages = int(response["pagination"]["totalPages"])

        return response, total_pages

    def _update_existing_beer(self, beer: Beer, beer_data: dict) -> None:
        beer.vmp_name = beer_data["name"]
        beer.main_category = beer_data["main_category"]["name"]

        if beer_data.get("main_sub_category"):
            beer.sub_category = beer_data["main_sub_category"]["name"]

        beer.country = beer_data["main_country"]["name"]
        beer.price = beer_data["price"]["value"]
        beer.volume = float(beer_data["volume"]["value"]) / 100.0
        beer.price_per_volume = self._calculate_price_per_volume(
            float(beer_data["price"]["value"]), float(beer_data["volume"]["value"])
        )
        beer.product_selection = beer_data["product_selection"]
        beer.vmp_url = f"https://www.vinmonopolet.no{beer_data['url']}"
        beer.post_delivery = parse_bool(
            beer_data["productAvailability"]["deliveryAvailability"][
                "availableForPurchase"
            ]
        )
        beer.store_delivery = (
            beer_data["productAvailability"]["storesAvailability"]["infos"][
                "readableValue"
            ]
            == "Kan bestilles til alle butikker"
        )
        beer.vmp_updated = timezone.now()

        if not beer.active:
            beer.active = True

        beer.save()

    def _create_new_beer(self, beer_data: dict) -> Beer:
        volume_value = float(beer_data["volume"]["value"])
        price_value = float(beer_data["price"]["value"])

        beer = Beer.objects.create(
            vmp_id=int(beer_data["code"]),
            vmp_name=beer_data["name"],
            main_category=beer_data["main_category"]["name"],
            country=beer_data["main_country"]["name"],
            price=price_value,
            volume=volume_value / 100.0,
            price_per_volume=self._calculate_price_per_volume(
                price_value, volume_value
            ),
            product_selection=beer_data["product_selection"],
            post_delivery=parse_bool(
                beer_data["productAvailability"]["deliveryAvailability"][
                    "availableForPurchase"
                ]
            ),
            store_delivery=(
                beer_data["productAvailability"]["storesAvailability"]["infos"][
                    "readableValue"
                ]
                == "Kan bestilles til alle butikker"
            ),
            vmp_url=f"https://www.vinmonopolet.no{beer_data['url']}",
            vmp_updated=timezone.now(),
        )

        if beer_data.get("main_sub_category"):
            beer.sub_category = beer_data["main_sub_category"]["name"]
            beer.save()

        return beer

    def _calculate_price_per_volume(self, price: float, volume_value: float) -> float:
        volume_in_liters = volume_value / 100.0
        return price / volume_in_liters
