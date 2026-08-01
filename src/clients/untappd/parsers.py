from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from clients.untappd.models import (
    UntappdBeer,
    UntappdBrewery,
    UntappdCheckin,
    UntappdListInfo,
    UntappdSearchResult,
)

UNTAPPD_BASE = "https://untappd.com"

_BEER_ID_RE = re.compile(r"/b(?:eer)?/[^/]+/(\d+)")
_LIST_ID_RE = re.compile(r"/lists/(\d+)")
_ITEM_COUNT_RE = re.compile(r"(\d+)\s*Item")


def normalize_url(url: str) -> str:
    return (
        url.replace("://", "PLACEHOLDER")
        .replace("//", "/")
        .replace("PLACEHOLDER", "://")
    )


def absolute_url(href: str) -> str:
    return href if href.startswith("http") else f"{UNTAPPD_BASE}{href}"


def _to_int(value: object) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _first_number(text: str, decimals: bool = False) -> str | None:
    pattern = r"\d+\.?\d*" if decimals else r"\b\d+\b"
    numbers = re.findall(pattern, text)
    return numbers[0] if numbers else None


def _beer_id_from_href(href: str) -> int | None:
    match = _BEER_ID_RE.search(href)
    if match:
        return int(match.group(1))
    return _to_int(href.rstrip("/").split("/")[-1])


def _json_ld(soup: BeautifulSoup) -> list[dict]:
    documents: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = getattr(script, "string", None)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            documents.append(data)
    return documents


def parse_search_results(html: str) -> list[UntappdSearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[UntappdSearchResult] = []

    for item in soup.select(".beer-item"):
        name_element = item.select_one(".name")
        link_element = item.select_one("a")
        if not name_element or not link_element:
            continue
        href = str(link_element.get("href") or "")
        untpd_id = _to_int(href.rstrip("/").split("/")[-1])
        if not href or untpd_id is None:
            continue
        results.append(
            UntappdSearchResult(
                name=name_element.text.strip(),
                untpd_id=untpd_id,
                url=absolute_url(href),
            )
        )

    return results


def parse_beer(html: str) -> UntappdBeer:
    soup = BeautifulSoup(html, "html.parser")
    documents = _json_ld(soup)
    beer = _parse_beer_json_ld(documents[0]) if documents else _parse_beer_html(soup)

    anchor = soup.select_one("p.brewery a")
    if anchor:
        href = str(anchor.get("href") or "")
        if href:
            beer.brewery_url = absolute_url(href)
            beer.brewery_name = anchor.text.strip() or None

    style_elem = soup.select_one("p.style")
    if style_elem:
        beer.style = style_elem.text.strip()

    abv_elem = soup.select_one("p.abv")
    if abv_elem:
        abv = _first_number(abv_elem.text, decimals=True)
        beer.abv = _to_float(abv) if abv else 0.0

    ibu_elem = soup.select_one("p.ibu")
    if ibu_elem:
        ibu = _first_number(ibu_elem.text)
        beer.ibu = _to_int(ibu) if ibu else None

    label_elem = soup.select_one("a.label.image-big")
    if label_elem:
        data_image = label_elem.get("data-image")
        if data_image:
            beer.label_hd_url = normalize_url(str(data_image))
        img_elem = label_elem.find("img")
        if img_elem:
            src = img_elem.get("src")
            if src:
                beer.label_sm_url = str(src)

    og_url = _og_url(soup)
    if og_url:
        beer.untpd_url = og_url

    return beer


def _parse_beer_json_ld(data: dict) -> UntappdBeer:
    rating = data.get("aggregateRating") or {}
    return UntappdBeer(
        untpd_id=_to_int(data.get("sku")),
        name=data.get("name"),
        rating=_to_float(rating.get("ratingValue")),
        checkins=_to_int(rating.get("reviewCount")),
        description=data.get("description"),
    )


def _parse_beer_html(soup: BeautifulSoup) -> UntappdBeer:
    beer = UntappdBeer()

    og_url = _og_url(soup)
    if og_url:
        beer.untpd_id = _to_int(og_url.rstrip("/").split("/")[-1])

    brewery_link = soup.select_one("p.brewery a")
    name_header = soup.select_one("div.name h1")
    if brewery_link and name_header:
        beer.name = f"{brewery_link.text} {name_header.text}".strip()

    caps_elem = soup.select_one("div.caps")
    if caps_elem:
        beer.rating = _to_float(caps_elem.get("data-rating"))

    raters_elem = soup.select_one("p.raters")
    if raters_elem:
        beer.checkins = _to_int(_first_number(raters_elem.text))

    desc_elem = soup.select_one("div.beer-descrption-read-less")
    if desc_elem:
        beer.description = desc_elem.text.strip()

    return beer


def parse_brewery(html: str) -> UntappdBrewery:
    soup = BeautifulSoup(html, "html.parser")
    brewery = UntappdBrewery()

    data = next(
        (doc for doc in _json_ld(soup) if doc.get("@type") == "Brewery"),
        None,
    )
    if data:
        brewery.name = data.get("name") or None
        brewery.description = data.get("description") or None
        image = _ld_image(data.get("image"))
        if image:
            brewery.label_url = normalize_url(image)

    if not brewery.label_url:
        label_elem = soup.select_one("a.label.image-big")
        data_image = label_elem.get("data-image") if label_elem else None
        if data_image:
            brewery.label_url = normalize_url(str(data_image))

    return brewery


def _ld_image(image: object) -> str | None:
    if isinstance(image, dict):
        return image.get("contentUrl") or image.get("url")
    if isinstance(image, str):
        return image
    return None


def parse_checkin(html: str) -> UntappdCheckin:
    soup = BeautifulSoup(html, "html.parser")
    return UntappdCheckin(
        beer_id=_parse_checkin_beer_id(soup),
        rating=_parse_checkin_rating(soup),
    )


def _parse_checkin_beer_id(soup: BeautifulSoup) -> int | None:
    beer_link = soup.select_one("a.label")
    if beer_link:
        beer_id = _beer_id_from_href(str(beer_link.get("href") or ""))
        if beer_id:
            return beer_id

    og_url = _og_url(soup)
    if og_url and "/beer/" in og_url:
        beer_id = _beer_id_from_href(og_url)
        if beer_id:
            return beer_id

    beer_name_link = soup.select_one("p.beer-name a")
    if beer_name_link:
        return _beer_id_from_href(str(beer_name_link.get("href") or ""))

    return None


def _parse_checkin_rating(soup: BeautifulSoup) -> float | None:
    caps_elem = soup.select_one("div.caps")
    if caps_elem:
        rating = _to_float(caps_elem.get("data-rating"))
        if rating:
            return rating

    rating_elem = soup.select_one("span.rating")
    if rating_elem:
        match = re.search(r"[\d.]+", rating_elem.text)
        if match:
            rating = _to_float(match.group())
            if rating:
                return rating

    return None


def parse_user_lists(html: str) -> list[UntappdListInfo]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[UntappdListInfo] = []

    for item in soup.select(".single-list"):
        name_el = item.select_one("h2")
        name = name_el.get_text(strip=True) if name_el else "Unnamed"
        count_el = item.select_one("h4")
        count_match = _ITEM_COUNT_RE.search(count_el.get_text()) if count_el else None
        count = int(count_match.group(1)) if count_match else 0

        if item.select_one("a[href*='/wishlist']"):
            results.append(UntappdListInfo(list_id=0, name=name, item_count=count))
            continue

        link = item.select_one("a[href*='/lists/']")
        if not link:
            continue
        list_id_match = _LIST_ID_RE.search(str(link.get("href") or ""))
        if not list_id_match:
            continue
        results.append(
            UntappdListInfo(
                list_id=int(list_id_match.group(1)), name=name, item_count=count
            )
        )

    return results


def parse_beer_ids(html: str) -> list[int]:
    soup = BeautifulSoup(html, "html.parser")
    beer_ids: list[int] = []
    for link in soup.select("a[href*='/b/']"):
        match = _BEER_ID_RE.search(str(link.get("href") or ""))
        if not match:
            continue
        beer_id = int(match.group(1))
        if beer_id not in beer_ids:
            beer_ids.append(beer_id)
    return beer_ids


def _og_url(soup: BeautifulSoup) -> str | None:
    og_url = soup.find("meta", property="og:url")
    if not og_url:
        return None
    content = og_url.get("content")
    return str(content) if content else None
