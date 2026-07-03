from __future__ import annotations

from beers.models import Store
from beers.vmp import VmpClient
from beers.vmp.commands import VmpCommand
from beers.vmp.models import VmpStore


class Command(VmpCommand):
    def handle(self, *args, **options) -> None:
        client = self.get_client()

        store_facets = client.iter_store_facets()

        self.stdout.write(f"Processing {len(store_facets)} stores...")

        updated = 0
        created = 0

        for facet in store_facets:
            if facet.code is None:
                continue
            result = self._process_store(client, facet.code)
            if result == "updated":
                updated += 1
            elif result == "created":
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Updated: {updated}, Created: {created}.")
        )

    def _process_store(self, client: VmpClient, store_code: str) -> str:
        details = client.get_store(store_code)
        fields = self._store_fields(details)
        if fields is None:
            return "skipped"

        _, created = Store.objects.update_or_create(
            store_id=int(store_code), defaults=fields
        )
        return "created" if created else "updated"

    def _store_fields(self, details: VmpStore) -> dict | None:
        address = details.address.line1
        zipcode = details.address.postal_code
        area = details.address.town
        category = details.assortment
        gps_lat = details.geo_point.latitude
        gps_long = details.geo_point.longitude

        if (
            address is None
            or zipcode is None
            or area is None
            or category is None
            or gps_lat is None
            or gps_long is None
        ):
            return None

        return {
            "name": details.display_name,
            "address": address,
            "zipcode": int(zipcode),
            "area": area,
            "category": category,
            "gps_lat": gps_lat,
            "gps_long": gps_long,
        }
