from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from django.db.models import Exists, OuterRef, Q

from beers.models import Stock

PRICE_BUCKETS = [0, 40, 60, 100, 150, 200, 300, 500, 750, 1000]
NAMED_SELECTIONS = ["Tilleggsutvalget", "Bestillingsutvalget", "Spesialutvalg"]

_NUMBER = r"(\d+(?:[.,]\d+)?)"
_RANGE = re.compile(rf"^{_NUMBER}\s*-\s*{_NUMBER}")
_PRICE_VALUE = re.compile(r"^\[(\*|\d+(?:\.\d+)?) TO (\*|\d+(?:\.\d+)?)\]$")
_VOLUME = re.compile(rf"^{_NUMBER}\s*-\s*{_NUMBER}\s*(cl|liter)$")
_VOLUME_OVER = re.compile(rf"^{_NUMBER} liter og over$")


@dataclass(frozen=True)
class VmpQuery:
    query: Q = field(default_factory=Q)
    ignored: list[str] = field(default_factory=list)


def _number(raw: str) -> float:
    return float(raw.replace(",", "."))


def _exact(name: str) -> Callable[[str], Q | None]:
    return lambda value: Q(**{name: value})


def _iexact(name: str) -> Callable[[str], Q | None]:
    return lambda value: Q(**{f"{name}__iexact": value})


def _flag(name: str) -> Callable[[str], Q | None]:
    return lambda value: Q(**{name: True}) if value == "true" else None


def _between(name: str, inclusive: bool = True) -> Callable[[str], Q | None]:
    upper = "lte" if inclusive else "lt"

    def build(value: str) -> Q | None:
        match = _RANGE.match(value)
        if match is None:
            return None
        return Q(
            **{
                f"{name}__gte": _number(match.group(1)),
                f"{name}__{upper}": _number(match.group(2)),
            }
        )

    return build


def _price(value: str) -> Q | None:
    if not value.isdigit() or int(value) not in PRICE_BUCKETS:
        return None
    low = int(value)
    index = PRICE_BUCKETS.index(low)
    if index + 1 == len(PRICE_BUCKETS):
        return Q(price__gte=low)
    return Q(price__gte=low, price__lt=PRICE_BUCKETS[index + 1])


def _price_value(value: str) -> Q | None:
    match = _PRICE_VALUE.match(value)
    if match is None:
        return None
    low, high = match.groups()
    query = Q()
    if low != "*":
        query &= Q(price__gte=float(low))
    if high != "*":
        query &= Q(price__lte=float(high))
    return query


def _volume(value: str) -> Q | None:
    over = _VOLUME_OVER.match(value)
    if over is not None:
        return Q(volume__gte=_number(over.group(1)))
    match = _VOLUME.match(value)
    if match is None:
        return None
    divisor = 100 if match.group(3) == "cl" else 1
    return Q(
        volume__gte=_number(match.group(1)) / divisor,
        volume__lte=_number(match.group(2)) / divisor,
    )


def _litre_price(value: str) -> Q | None:
    try:
        price = float(value)
    except ValueError:
        return None
    return Q(price_per_volume__gte=price - 0.01, price_per_volume__lte=price + 0.01)


def _store(value: str) -> Q | None:
    if not value.isdigit():
        return None
    stocked = Stock.objects.filter(beer=OuterRef("pk"), store=int(value)).exclude(
        quantity=0
    )
    return Q(Exists(stocked))


def _selection(value: str) -> Q | None:
    if value == "AndreUtvalg":
        return ~Q(product_selection__in=NAMED_SELECTIONS)
    return Q(product_selection__iexact=value)


FACETS: dict[str, Callable[[str], Q | None]] = {
    "mainCategory": lambda v: Q(main_category_code=v) | Q(main_category__iexact=v),
    "mainSubCategory": _exact("sub_category_code"),
    "mainCountry": lambda v: Q(country__vmp_code=v) | Q(country__name__iexact=v),
    "mainDistrict": _exact("district_code"),
    "mainSubDistrict": _exact("sub_district_code"),
    "brand": _exact("producer_code"),
    "mainWholesaler": _iexact("wholesaler"),
    "price": _price,
    "priceValue": _price_value,
    "litrePrice": _litre_price,
    "volumeRanges": _volume,
    "alcohol": _between("vmp_abv", inclusive=False),
    "Sukker": _between("sugar"),
    "Fylde": _between("fullness"),
    "Friskhet": _between("freshness"),
    "Bitterhet": _between("bitterness"),
    "isGoodfor": lambda v: Q(food_pairing_codes__contains=[v]),
    "year": lambda v: Q(year=int(v)) if v.isdigit() else None,
    "Emballasjetype": _iexact("package_material"),
    "Lagringsgrad": _iexact("storable"),
    "Raastoff": lambda v: Q(raw_materials__icontains=v),
    "StockAvailability": _selection,
    "availableInStores": _store,
    "Eco": _flag("eco"),
    "Gluten": _flag("gluten_free"),
    "miljoEmballasje": _flag("climate_smart_packaging"),
    "vegan": _flag("vegan"),
    "newProducts": _flag("is_new"),
    "inStock": _flag("post_delivery"),
    "buyable": _flag("active"),
    "buyableBy18YearOlds": lambda v: Q(age_limit=18) if v == "true" else None,
}


def parse_vmp_query(raw: str) -> VmpQuery:
    tokens = raw.split(":")
    text = tokens[0].strip()
    pairs = tokens[2:]
    grouped: dict[str, list[str]] = {}
    for index in range(0, len(pairs) - 1, 2):
        grouped.setdefault(pairs[index], []).append(pairs[index + 1].strip())

    query = Q()
    ignored: list[str] = []
    for facet, values in grouped.items():
        build = FACETS.get(facet)
        parts = (
            [part for part in map(build, values) if part is not None] if build else []
        )
        if len(parts) != len(values):
            ignored.append(facet)
            continue
        facet_query = Q()
        for part in parts:
            facet_query |= part
        query &= facet_query

    for word in text.split():
        query &= (
            Q(vmp_name__icontains=word)
            | Q(vmp_brewery__icontains=word)
            | Q(brewery__name__icontains=word)
            | Q(sub_category__icontains=word)
            | Q(style__icontains=word)
        )

    return VmpQuery(query=query, ignored=ignored)
