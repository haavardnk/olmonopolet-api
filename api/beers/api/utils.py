from __future__ import annotations

from beers.models import Country


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
