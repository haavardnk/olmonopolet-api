from __future__ import annotations

from argparse import ArgumentParser

from beers.models import Badge
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("badge_type", type=str, help="Type of badges to remove")

    def handle(self, *args, **options) -> None:
        badge_type = options["badge_type"]

        badges_to_delete = Badge.objects.filter(type=badge_type)
        count = badges_to_delete.count()

        if not count:
            self.stdout.write(
                self.style.WARNING(f"No badges found with type '{badge_type}'")
            )
            return

        badges_to_delete.delete()

        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} badges of type '{badge_type}'")
        )
