from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

from beers.models import Beer, Country, Tasted, UntappdCheckin
from django.contrib.auth.models import User
from django.db import transaction

CheckinTuple = tuple[int, float | None, datetime | None]
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S %z")
_EMPTY_SYNC_RESULT: dict[str, int] = {"synced_count": 0, "users_affected": 0}


def parse_bool(val: str | bool) -> bool:
    if isinstance(val, bool):
        return val

    if isinstance(val, str):
        normalized = val.strip().lower()
        if normalized in ("true", "t", "1", "yes", "y", "on"):
            return True
        if normalized in ("false", "f", "0", "no", "n", "off", ""):
            return False

    raise ValueError(f"Invalid truth value: {val!r}")


def get_or_create_country(country_name: str | None) -> Country | None:
    if not country_name:
        return None

    country, created = Country.objects.get_or_create(
        name=country_name, defaults={"iso_code": None}
    )

    if created:
        print(f"New country created: {country_name} - needs ISO mapping in admin")

    return country


def _parse_checkin_time(raw: str | int | float | None) -> datetime | None:
    if not raw:
        return None

    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (ValueError, OSError):
            return None

    for fmt in _DATETIME_FORMATS:
        try:
            dt = datetime.strptime(str(raw).strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _extract_checkin_data(row: dict) -> CheckinTuple | None:
    beer_id = row.get("bid") or row.get("beer_id")

    if not beer_id and (url := row.get("beer_url")):
        try:
            beer_id = url.rstrip("/").split("/")[-1]
        except (AttributeError, IndexError):
            pass

    if not beer_id:
        return None

    try:
        beer_id = int(beer_id)
    except (ValueError, TypeError):
        return None

    rating = None
    if rating_str := row.get("rating_score"):
        try:
            rating = float(rating_str) or None
        except (ValueError, TypeError):
            pass

    return (beer_id, rating, _parse_checkin_time(row.get("created_at")))


def parse_untappd_file(uploaded_file) -> list[CheckinTuple] | None:
    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        decoded = uploaded_file.read().decode("utf-8").splitlines()
        return [
            data
            for row in csv.DictReader(decoded)
            if (data := _extract_checkin_data(row))
        ]

    if filename.endswith(".json"):
        data = json.load(uploaded_file)
        if not isinstance(data, list):
            return []
        return [checkin for item in data if (checkin := _extract_checkin_data(item))]

    return None


def _dedup_checkins(
    checkins: list[CheckinTuple],
) -> dict[int, tuple[float | None, datetime | None]]:
    best: dict[int, tuple[float | None, datetime | None]] = {}
    for beer_id, rating, checkin_at in checkins:
        prev_rating, prev_at = best.get(beer_id, (None, None))
        keep_rating = _pick_higher(prev_rating, rating)
        keep_at = _pick_earlier(prev_at, checkin_at)
        best[beer_id] = (keep_rating, keep_at)
    return best


def _pick_higher(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _pick_earlier(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _save_checkins(
    user: User, deduped: dict[int, tuple[float | None, datetime | None]]
) -> None:
    existing = {
        c.untpd_beer_id: c
        for c in UntappdCheckin.objects.filter(
            user=user, untpd_beer_id__in=deduped.keys()
        )
    }

    new_ids = deduped.keys() - existing.keys()
    if new_ids:
        UntappdCheckin.objects.bulk_create(
            [
                UntappdCheckin(
                    user=user,
                    untpd_beer_id=uid,
                    rating=deduped[uid][0],
                    checkin_at=deduped[uid][1],
                )
                for uid in new_ids
            ]
        )

    to_update: list[UntappdCheckin] = []
    for untpd_id, (rating, checkin_at) in deduped.items():
        checkin = existing.get(untpd_id)
        if not checkin:
            continue
        new_rating = _pick_higher(checkin.rating, rating)
        new_at = _pick_earlier(checkin.checkin_at, checkin_at)
        if new_rating != checkin.rating or new_at != checkin.checkin_at:
            checkin.rating = new_rating
            checkin.checkin_at = new_at
            to_update.append(checkin)
    if to_update:
        UntappdCheckin.objects.bulk_update(to_update, ["rating", "checkin_at"])


def _sync_matched_checkins(
    user: User, deduped: dict[int, tuple[float | None, datetime | None]]
) -> int:
    untpd_to_beer = {
        b.untpd_id: b for b in Beer.objects.filter(untpd_id__in=deduped.keys())
    }
    if not untpd_to_beer:
        return 0

    existing_tasted = set(
        Tasted.objects.filter(
            user=user, beer__untpd_id__in=untpd_to_beer.keys()
        ).values_list("beer__untpd_id", flat=True)
    )

    tasted_to_create = [
        Tasted(user=user, beer=beer, rating=deduped[uid][0])
        for uid, beer in untpd_to_beer.items()
        if uid not in existing_tasted
    ]
    if tasted_to_create:
        Tasted.objects.bulk_create(tasted_to_create)

    UntappdCheckin.objects.filter(
        user=user, untpd_beer_id__in=untpd_to_beer.keys()
    ).update(synced=True)

    return len(tasted_to_create)


def bulk_import_tasted(user: User, checkins: list[CheckinTuple]) -> dict[str, int]:
    deduped = _dedup_checkins(checkins)
    with transaction.atomic():
        _save_checkins(user, deduped)
        imported_count = _sync_matched_checkins(user, deduped)

    return {
        "imported_count": imported_count,
        "total_check_ins": len(checkins),
    }


def sync_unmatched_checkins() -> dict[str, int]:
    unsynced = UntappdCheckin.objects.filter(synced=False)
    if not unsynced.exists():
        return _EMPTY_SYNC_RESULT

    untpd_ids = set(unsynced.values_list("untpd_beer_id", flat=True))
    untpd_to_beer = {b.untpd_id: b for b in Beer.objects.filter(untpd_id__in=untpd_ids)}
    if not untpd_to_beer:
        return _EMPTY_SYNC_RESULT

    matchable = unsynced.filter(untpd_beer_id__in=untpd_to_beer.keys())

    existing_tasted = set(
        Tasted.objects.filter(beer__untpd_id__in=untpd_to_beer.keys()).values_list(
            "user_id", "beer__untpd_id"
        )
    )

    tasted_to_create: list[Tasted] = []
    users_affected: set[int] = set()
    checkin_ids_to_mark: list[int] = []

    for checkin in matchable:
        key = (checkin.user_id, checkin.untpd_beer_id)
        if key not in existing_tasted:
            tasted_to_create.append(
                Tasted(
                    user_id=checkin.user_id,
                    beer=untpd_to_beer[checkin.untpd_beer_id],
                    rating=checkin.rating,
                )
            )
            existing_tasted.add(key)
            users_affected.add(checkin.user_id)
        checkin_ids_to_mark.append(checkin.id)

    if tasted_to_create:
        Tasted.objects.bulk_create(tasted_to_create)
    if checkin_ids_to_mark:
        UntappdCheckin.objects.filter(id__in=checkin_ids_to_mark).update(synced=True)

    return {
        "synced_count": len(tasted_to_create),
        "users_affected": len(users_affected),
    }
