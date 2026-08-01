from __future__ import annotations

import logging

from beers.models import UntappdList, UserList
from clients.untappd import UntappdClient, UntappdListNotFound
from django.utils import timezone

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
