from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import cloudscraper25
import sentry_sdk
from beers.models import Option, UntappdList
from bs4 import BeautifulSoup
from cloudscraper25 import CloudScraper
from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)

UNTAPPD_BASE = "https://untappd.com"
REQUEST_DELAY = 2


class UntappdCookieExpired(Exception):
    pass


class UntappdListNotFound(Exception):
    pass


@dataclass
class UntappdListInfo:
    list_id: int
    name: str
    item_count: int


def fetch_user_lists(username: str) -> list[UntappdListInfo]:
    scraper = cloudscraper25.create_scraper()
    url = f"{UNTAPPD_BASE}/user/{username}/lists"
    resp = scraper.get(url, timeout=30)

    if resp.status_code == 404:
        raise ValueError(f"Untappd user '{username}' not found")
    if "set their account to be private" in resp.text:
        raise ValueError(f"Untappd user '{username}' has a private profile")

    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_user_lists_page(soup)


def _parse_user_lists_page(soup: BeautifulSoup) -> list[UntappdListInfo]:
    results: list[UntappdListInfo] = []
    list_items = soup.select(".single-list")

    for item in list_items:
        name_el = item.select_one("h2")
        name = name_el.get_text(strip=True) if name_el else "Unnamed"
        count_el = item.select_one("h4")
        count = 0
        if count_el:
            count_match = re.search(r"(\d+)\s*Item", count_el.get_text())
            if count_match:
                count = int(count_match.group(1))

        wishlist_link = item.select_one("a[href*='/wishlist']")
        if wishlist_link:
            results.append(
                UntappdListInfo(list_id=0, name=name, item_count=count)
            )
            continue

        link = item.select_one("a[href*='/lists/']")
        if not link:
            continue
        href = str(link.get("href", ""))
        list_id_match = re.search(r"/lists/(\d+)", href)
        if not list_id_match:
            continue

        list_id = int(list_id_match.group(1))
        results.append(UntappdListInfo(list_id=list_id, name=name, item_count=count))

    return results


def fetch_list_beer_ids(
    username: str, list_id: int, scraper: CloudScraper | None = None
) -> list[int]:
    if not scraper:
        scraper = cloudscraper25.create_scraper()

    _inject_session_cookies(scraper)

    if list_id == 0:
        return _fetch_wishlist_beer_ids(scraper, username)

    initial = _fetch_initial_page_ids(scraper, username, list_id)
    if initial is None:
        raise UntappdListNotFound(
            f"List {list_id} for user '{username}' is not accessible"
        )

    beer_ids: list[int] = initial

    offset = len(beer_ids)
    for _ in range(100):
        url = f"{UNTAPPD_BASE}/profile/more_list_items/{username}/{list_id}/{offset}"
        resp = scraper.get(
            url,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/html, */*; q=0.01",
                "Referer": f"{UNTAPPD_BASE}/user/{username}/lists/{list_id}",
            },
            timeout=30,
        )

        if resp.status_code != 200 or not resp.text.strip():
            break

        page_ids = _parse_beer_ids_from_html(resp.text, list_id)
        if not page_ids:
            break

        beer_ids.extend(page_ids)
        offset = len(beer_ids)
        time.sleep(REQUEST_DELAY)

    return beer_ids


def _fetch_wishlist_beer_ids(scraper: CloudScraper, username: str) -> list[int]:
    beer_ids: list[int] = []
    offset = 0
    for _ in range(100):
        url = f"{UNTAPPD_BASE}/apireqs/userwishlist/{username}/{offset}"
        resp = scraper.get(
            url,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        items = data.get("data", {}).get("beers", {}).get("items", [])
        if not items:
            break
        for item in items:
            bid = item.get("beer", {}).get("bid")
            if bid and bid not in beer_ids:
                beer_ids.append(bid)
        total = data.get("data", {}).get("total_count", 0)
        if len(beer_ids) >= total:
            break
        offset = len(beer_ids)
        time.sleep(REQUEST_DELAY)
    return beer_ids


def _inject_session_cookies(scraper: CloudScraper) -> None:
    try:
        option = Option.objects.get(name="untappd_user_v3_e")
    except Option.DoesNotExist:
        return
    if not option.value:
        return

    scraper.get(f"{UNTAPPD_BASE}/", timeout=30)
    scraper.cookies.set("untappd_user_v3_e", option.value)


def _fetch_initial_page_ids(
    scraper: CloudScraper, username: str, list_id: int
) -> list[int] | None:
    url = f"{UNTAPPD_BASE}/user/{username}/lists/{list_id}"
    resp = scraper.get(url, timeout=30)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        return []
    if "set their account to be private" in resp.text:
        return None
    if "action=\"login\"" in resp.text or "/login" in resp.url:
        exc = UntappdCookieExpired("Untappd session cookie has expired")
        sentry_sdk.capture_exception(exc)
        logger.warning("Untappd cookie expired during list fetch")
        return []
    return _parse_beer_ids_from_html(resp.text, list_id)


def _parse_beer_ids_from_html(html: str, list_id: int) -> list[int]:
    soup = BeautifulSoup(html, "html.parser")
    beer_ids: list[int] = []
    for link in soup.select("a[href*='/b/']"): 
        href = str(link.get("href", ""))
        m = re.search(r"/b/[^/]+/(\d+)", href)
        if m:
            bid = int(m.group(1))
            if bid not in beer_ids:
                beer_ids.append(bid)
    return beer_ids


def sync_untappd_list(
    untappd_list: UntappdList, scraper: CloudScraper | None = None
) -> int:
    try:
        beer_ids = fetch_list_beer_ids(
            untappd_list.untappd_username,
            untappd_list.untappd_list_id,
            scraper,
        )
    except UntappdListNotFound:
        logger.info(
            "List %s/%s no longer accessible, deactivating",
            untappd_list.untappd_username,
            untappd_list.untappd_list_id,
        )
        untappd_list.active = False
        untappd_list.save(update_fields=["active"])
        from beers.models import UserList

        UserList.objects.filter(untappd_list=untappd_list).delete()
        raise

    untappd_list.untappd_beer_ids = beer_ids
    untappd_list.item_count = len(beer_ids)
    untappd_list.last_synced = dj_timezone.now()
    untappd_list.save(update_fields=["untappd_beer_ids", "item_count", "last_synced"])
    return len(beer_ids)
