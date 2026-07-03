from __future__ import annotations

from beers.models import Beer, VmpNotReleased
from beers.vmp import VmpApiError
from beers.vmp.commands import VmpCommand, apply_product_fields
from beers.vmp.models import VmpProduct
from django.core.management.base import CommandError


class Command(VmpCommand):
    def handle(self, *args, **options) -> None:
        client = self.get_client()

        products = VmpNotReleased.objects.all()

        if not products.exists():
            self.stdout.write(self.style.WARNING("No unreleased products found"))
            return

        self.stdout.write(f"Processing {products.count()} unreleased products...")

        updated = 0
        created = 0
        failed = 0

        for product in products:
            try:
                detail = client.get_product(product.id)
            except VmpApiError:
                failed += 1
                continue

            if self._save_beer(detail):
                updated += 1
            else:
                created += 1
            product.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers and created {created} new beers!"
            )
        )

        if failed and updated + created == 0:
            raise CommandError(
                f"All {failed} unreleased lookups failed (vinmonopolet unreachable)"
            )

    def _save_beer(self, product: VmpProduct) -> bool:
        code = int(product.code)
        try:
            beer = Beer.objects.get(vmp_id=code)
            is_update = True
        except Beer.DoesNotExist:
            beer = Beer(vmp_id=code)
            is_update = False

        apply_product_fields(beer, product)
        beer.save()
        return is_update
