from __future__ import annotations

import csv
import json

from beers.models import Country


def extract_checkin_data(row: dict) -> tuple[int, float | None] | None:
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


def parse_untappd_csv(uploaded_file) -> list[tuple[int, float | None]]:
    decoded = uploaded_file.read().decode("utf-8").splitlines()
    return [
        data for row in csv.DictReader(decoded) if (data := extract_checkin_data(row))
    ]


def parse_untappd_json(uploaded_file) -> list[tuple[int, float | None]]:
    data = json.load(uploaded_file)
    if not isinstance(data, list):
        return []
    return [checkin for item in data if (checkin := extract_checkin_data(item))]


def parse_untappd_file(uploaded_file) -> list[tuple[int, float | None]] | None:
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        return parse_untappd_csv(uploaded_file)
    if filename.endswith(".json"):
        return parse_untappd_json(uploaded_file)
    return None


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


def get_or_create_country(country_name):
    if not country_name:
        return None

    country, created = Country.objects.get_or_create(
        name=country_name, defaults={"iso_code": None}
    )

    if created:
        print(f"New country created: {country_name} - needs ISO mapping in admin")

    return country
