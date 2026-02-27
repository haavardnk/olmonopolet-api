from __future__ import annotations

from beers.api.utils import sync_unmatched_checkins
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync unmatched Untappd checkins to tasted when matching beers exist"

    def handle(self, *args, **options):
        result = sync_unmatched_checkins()
        self.stdout.write(
            f"Synced {result['synced_count']} tastings for {result['users_affected']} users"
        )
