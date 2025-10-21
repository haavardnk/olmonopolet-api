from __future__ import annotations

from beers.models import Beer
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options) -> None:
        beers_with_flag = Beer.objects.filter(match_manually=True)
        count = beers_with_flag.count()

        if not count:
            self.stdout.write(
                self.style.WARNING("No beers found with match_manually flag set")
            )
            return

        updated_count = beers_with_flag.update(match_manually=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Removed match_manually flag from {updated_count} beers"
            )
        )
