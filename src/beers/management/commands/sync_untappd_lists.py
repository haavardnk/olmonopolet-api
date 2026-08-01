from __future__ import annotations

import json
import logging
from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from beers.models import UntappdList, UserList
from clients.untappd import UntappdClient, UntappdListNotFound

logger = logging.getLogger(__name__)


def sync_untappd_list(
    untappd_list: UntappdList, client: UntappdClient | None = None
) -> int:
    client = client or UntappdClient.from_options()

    try:
        beer_ids = client.fetch_list_beer_ids(
            untappd_list.untappd_username,
            untappd_list.untappd_list_id,
        )
    except UntappdListNotFound:
        logger.info(
            "List %s/%s no longer accessible, deactivating",
            untappd_list.untappd_username,
            untappd_list.untappd_list_id,
        )
        untappd_list.active = False
        untappd_list.save(update_fields=["active"])
        UserList.objects.filter(untappd_list=untappd_list).delete()
        raise

    untappd_list.untappd_beer_ids = beer_ids
    untappd_list.item_count = len(beer_ids)
    untappd_list.last_synced = timezone.now()
    untappd_list.save(update_fields=["untappd_beer_ids", "item_count", "last_synced"])
    return len(beer_ids)


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

        client = UntappdClient.from_options()
        total_synced = 0
        failed = 0

        for untappd_list in lists:
            self.stdout.write(
                f"Syncing: {untappd_list.untappd_username}/{untappd_list.name}"
            )
            try:
                count = sync_untappd_list(untappd_list, client)
                total_synced += 1
                self.stdout.write(f"  Found {count} beers")
            except UntappdListNotFound:
                self.stdout.write(self.style.ERROR("  Not found, marked inactive"))
            except Exception as e:
                logger.exception(
                    "Failed syncing list %s/%s",
                    untappd_list.untappd_username,
                    untappd_list.untappd_list_id,
                )
                self.stdout.write(self.style.ERROR(f"  Failed: {e}"))
                failed += 1

        summary = json.dumps({"synced": total_synced, "total": lists.count()})
        self.stdout.write(summary)

        if failed and total_synced == 0:
            raise CommandError(f"All {failed} list syncs failed (untappd unreachable)")
