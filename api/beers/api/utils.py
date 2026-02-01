from __future__ import annotations

import csv
import json

from beers.models import Beer, Country, Tasted


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


def _extract_checkin_data(row: dict) -> tuple[int, float | None] | None:
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
            rating = float(rating_str)
            if rating == 0:
                rating = None
        except (ValueError, TypeError):
            pass

    return (beer_id, rating)


def parse_untappd_file(uploaded_file) -> list[tuple[int, float | None]] | None:
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


def bulk_import_tasted(
    user, checkins: list[tuple[int, float | None]]
) -> dict[str, int]:
    rating_map: dict[int, float | None] = {}
    for beer_id, rating in checkins:
        if beer_id not in rating_map or (
            rating is not None
            and (rating_map[beer_id] is None or rating > rating_map[beer_id])
        ):
            rating_map[beer_id] = rating

    beers = Beer.objects.filter(untpd_id__in=list(rating_map.keys()))
    untpd_to_beer = {beer.untpd_id: beer for beer in beers}

    existing = set(
        Tasted.objects.filter(user=user, beer__in=beers).values_list(
            "beer__untpd_id", flat=True
        )
    )

    to_create = [
        Tasted(user=user, beer=untpd_to_beer[untpd_id], rating=rating)
        for untpd_id, rating in rating_map.items()
        if untpd_id in untpd_to_beer and untpd_id not in existing
    ]
    Tasted.objects.bulk_create(to_create)

    return {
        "imported_count": len(to_create),
        "total_check_ins": len(checkins),
    }
