from __future__ import annotations

import re
from argparse import ArgumentParser

import cloudscraper25
import xmltodict
from beers.models import Beer, ExternalAPI, Stock, Store
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("stores", type=int, help="Number of stores to process")

    def handle(self, *args, **options) -> None:
        try:
            baseurl = ExternalAPI.objects.get(name="vinmonopolet").baseurl
        except ExternalAPI.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("vinmonopolet external API configuration not found")
            )
            return

        url = f"{baseurl}products/search/"
        stores_limit = options["stores"]

        stores = Store.objects.all().order_by("store_stock_updated")[:stores_limit]

        if not stores:
            self.stdout.write(self.style.WARNING("No stores found to update"))
            return

        self.stdout.write(f"Processing {len(stores)} stores...")

        updated = 0
        stocked = 0
        unstocked = 0
        stores_updated = 0

        for store in stores.iterator():
            store_updated, store_stocked, store_unstocked = self._update_store_stock(
                url, store
            )
            updated += store_updated
            stocked += store_stocked
            unstocked += store_unstocked
            stores_updated += 1

            self.stdout.write(
                f"Store {store.name}: Updated {store_updated}, Stocked {store_stocked}, "
                f"Unstocked {store_unstocked} | Total: {stores_updated}/{len(stores)}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated stock: {updated} Stocked: {stocked} "
                f"Out of stock: {unstocked} Stores updated: {stores_updated}/{len(stores)}"
            )
        )

    def _update_store_stock(self, url: str, store: Store) -> tuple[int, int, int]:
        updated = 0
        stocked = 0
        unstocked = 0
        stocked_beers: list[Beer] = []

        products = [
            "øl",
            "sider",
            "mjød",
            "alkoholfritt_alkoholfritt_øl",
            "alkoholfritt_alkoholfri_ingefærøl",
            "alkoholfritt_alkoholfri_sider",
        ]

        for product in products:
            product_updated, product_stocked, product_beers = (
                self._process_product_for_store(url, store, product)
            )
            updated += product_updated
            stocked += product_stocked
            stocked_beers.extend(product_beers)

        if stocked_beers:
            unstocked = self._unstock_missing_beers(store, stocked_beers)

        store.store_stock_updated = timezone.now()
        store.save()

        return updated, stocked, unstocked

    def _process_product_for_store(
        self, url: str, store: Store, product: str
    ) -> tuple[int, int, list[Beer]]:
        updated = 0
        stocked = 0
        stocked_beers: list[Beer] = []

        try:
            response, total_pages = self._call_api(url, store.store_id, 0, product)

            for page in range(total_pages):
                try:
                    response, _ = self._call_api(url, store.store_id, page, product)

                    for product_data in response.get("products", []):
                        try:
                            beer = Beer.objects.get(vmp_id=int(product_data["code"]))
                            stocked_beers.append(beer)

                            quantity = self._extract_quantity(product_data)
                            beer_updated, beer_stocked = self._update_beer_stock(
                                store, beer, quantity
                            )

                            updated += beer_updated
                            stocked += beer_stocked

                        except Beer.DoesNotExist:
                            continue

                except Exception:
                    continue

        except Exception:
            pass

        return updated, stocked, stocked_beers

    def _call_api(
        self, url: str, store_id: int, page: int, product: str
    ) -> tuple[dict, int]:
        if "alkoholfritt" in product:
            query = (
                f":name-asc:visibleInSearch:true:mainCategory:alkoholfritt:"
                f"mainSubCategory:{product}:availableInStores:{store_id}:"
            )
        else:
            query = (
                f":name-asc:visibleInSearch:true:mainCategory:{product}:"
                f"availableInStores:{store_id}:"
            )

        req_url = f"{url}?currentPage={page}&fields=FULL&pageSize=100&query={query}"

        scraper = cloudscraper25.create_scraper(interpreter="nodejs")
        response_text = scraper.get(req_url).text
        response_data = xmltodict.parse(response_text)["productCategorySearchPage"]
        total_pages = int(response_data["pagination"]["totalPages"])

        return response_data, total_pages

    def _extract_quantity(self, product_data: dict) -> int:
        availability_text = product_data["productAvailability"]["storesAvailability"][
            "infos"
        ]["availability"]
        quantities = re.findall(r"\b\d+\b", availability_text)
        return int(quantities[0]) if quantities else 0

    def _update_beer_stock(
        self, store: Store, beer: Beer, quantity: int
    ) -> tuple[int, int]:
        try:
            stock = Stock.objects.get(store=store, beer=beer)
            if stock.quantity == 0 and quantity != 0:
                stock.stocked_at = timezone.now()
            stock.quantity = quantity
            stock.save()
            return 1, 0

        except Stock.DoesNotExist:
            Stock.objects.create(
                store=store,
                beer=beer,
                quantity=quantity,
                stocked_at=timezone.now(),
            )
            return 0, 1

    def _unstock_missing_beers(self, store: Store, stocked_beers: list[Beer]) -> int:
        stocks_to_unstock = (
            Stock.objects.filter(store=store)
            .exclude(beer__in=stocked_beers)
            .exclude(quantity=0)
        )

        count = stocks_to_unstock.count()

        for stock in stocks_to_unstock:
            stock.quantity = 0
            stock.unstocked_at = timezone.now()
            stock.save()

        return count
