from __future__ import annotations

import json
from argparse import ArgumentParser

import cloudscraper25
from beers.models import UntappdList
from beers.untappd_lists import sync_untappd_list
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync all active Untappd lists"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--list-id",
            type=int,
            default=None,
            help="Sync only a specific UntappdList by its untappd_list_id",
        )

    def handle(self, *args, **options) -> None:
        lists = UntappdList.objects.filter(active=True)
        if options["list_id"]:
            lists = lists.filter(untappd_list_id=options["list_id"])

        if not lists.exists():
            self.stdout.write("No active Untappd lists found")
            return

        scraper = cloudscraper25.create_scraper()
        total_synced = 0

        for untappd_list in lists:
            self.stdout.write(
                f"Syncing: {untappd_list.untappd_username}/{untappd_list.name}"
            )
            try:
                count = sync_untappd_list(untappd_list, scraper)
                total_synced += 1
                self.stdout.write(f"  Found {count} beers")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  Failed: {e}")
                )
                if "not found" in str(e) or "private" in str(e):
                    untappd_list.active = False
                    untappd_list.save(update_fields=["active"])
                    self.stdout.write("  Marked inactive")

        summary = json.dumps({"synced": total_synced, "total": lists.count()})
        self.stdout.write(summary)
