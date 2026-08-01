from __future__ import annotations

import logging
import time

import cloudscraper25
import feedparser
import sentry_sdk
from requests import Response, Session

from beers.models import Option
from clients.untappd import parsers
from clients.untappd.models import (
    UntappdBeer,
    UntappdBrewery,
    UntappdCheckin,
    UntappdListInfo,
    UntappdSearchResult,
)

logger = logging.getLogger(__name__)

UNTAPPD_BASE = parsers.UNTAPPD_BASE
COOKIE_NAME = "untappd_user_v3_e"
REQUEST_DELAY = 2
_TIMEOUT = 30
_MAX_PAGES = 100
_AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html, */*; q=0.01",
}


class UntappdError(Exception):
    pass


class UntappdCookieExpired(UntappdError):
    pass


class UntappdListNotFound(UntappdError):
    pass


def generate_query_variations(beer_name: str) -> list[str]:
    variations = [beer_name]

    if " x " in beer_name:
        main_brewery, rest = beer_name.split(" x ", 1)
        collab_removed = f"{main_brewery.strip()} {rest.strip()}"
        variations.append(collab_removed)
    else:
        collab_removed = beer_name

    words = collab_removed.split()
    variations.extend(" ".join(words[:i]) for i in range(len(words) - 1, 2, -1))

    return variations


class UntappdClient:
    def __init__(
        self,
        session_cookie: str = "",
        request_delay: float = REQUEST_DELAY,
        scraper: Session | None = None,
    ) -> None:
        self._cookie = session_cookie
        self._delay = request_delay
        self._scraper = scraper or cloudscraper25.create_scraper(
            browser="chrome", enable_stealth=True
        )
        self._cookie_injected = False

    @classmethod
    def from_options(
        cls,
        request_delay: float = REQUEST_DELAY,
        scraper: Session | None = None,
    ) -> UntappdClient:
        option = Option.objects.filter(name=COOKIE_NAME).first()
        return cls(option.value if option else "", request_delay, scraper)

    def search_beers(self, query: str) -> list[UntappdSearchResult]:
        response = self._scraper.get(
            f"{UNTAPPD_BASE}/search?q={query}", timeout=_TIMEOUT
        )
        if response.status_code != 200:
            return []
        return parsers.parse_search_results(response.text)

    def get_beer(self, url: str) -> UntappdBeer | None:
        html = self._get_page(url)
        return parsers.parse_beer(html) if html is not None else None

    def get_brewery(self, url: str) -> UntappdBrewery | None:
        html = self._get_page(url)
        return parsers.parse_brewery(html) if html is not None else None

    def get_checkin(self, url: str) -> UntappdCheckin | None:
        html = self._get_page(url)
        return parsers.parse_checkin(html) if html is not None else None

    def fetch_rss_entries(self, feed_url: str) -> list[dict] | None:
        parsed = feedparser.parse(feed_url)
        if parsed.bozo and not parsed.entries:
            return None
        return list(parsed.entries)

    def fetch_user_lists(self, username: str) -> list[UntappdListInfo]:
        self._inject_cookie()
        response = self._scraper.get(
            f"{UNTAPPD_BASE}/user/{username}/lists", timeout=_TIMEOUT
        )

        if response.status_code == 404:
            raise ValueError(f"Untappd user '{username}' not found")
        if "set their account to be private" in response.text:
            raise ValueError(f"Untappd user '{username}' has a private profile")
        self._check_cookie(response, "user lists fetch")

        response.raise_for_status()
        return parsers.parse_user_lists(response.text)

    def fetch_list_beer_ids(self, username: str, list_id: int) -> list[int]:
        self._inject_cookie()
        if list_id == 0:
            return self._fetch_wishlist_beer_ids(username)

        beer_ids = self._fetch_list_first_page(username, list_id)
        offset = len(beer_ids)

        for _ in range(_MAX_PAGES):
            url = (
                f"{UNTAPPD_BASE}/profile/more_list_items/{username}/{list_id}/{offset}"
            )
            response = self._scraper.get(
                url,
                headers={
                    **_AJAX_HEADERS,
                    "Referer": f"{UNTAPPD_BASE}/user/{username}/lists/{list_id}",
                },
                timeout=_TIMEOUT,
            )
            if response.status_code != 200 or not response.text.strip():
                break

            page_ids = parsers.parse_beer_ids(response.text)
            if not page_ids:
                break

            beer_ids.extend(page_ids)
            offset = len(beer_ids)
            time.sleep(self._delay)

        return beer_ids

    def _fetch_list_first_page(self, username: str, list_id: int) -> list[int]:
        url = f"{UNTAPPD_BASE}/user/{username}/lists/{list_id}"
        response = self._scraper.get(url, timeout=_TIMEOUT)

        if response.status_code == 404:
            raise UntappdListNotFound(
                f"List {list_id} for user '{username}' is not accessible"
            )
        if response.status_code != 200:
            return []
        if "set their account to be private" in response.text:
            raise UntappdListNotFound(
                f"List {list_id} for user '{username}' is not accessible"
            )
        if self._cookie_expired(response):
            self._expired_cookie_error("list fetch")
            return []

        return parsers.parse_beer_ids(response.text)

    def _fetch_wishlist_beer_ids(self, username: str) -> list[int]:
        beer_ids: list[int] = []
        offset = 0

        for _ in range(_MAX_PAGES):
            response = self._scraper.get(
                f"{UNTAPPD_BASE}/apireqs/userwishlist/{username}/{offset}",
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=_TIMEOUT,
            )
            if response.status_code != 200:
                break

            data = response.json().get("data", {})
            items = data.get("beers", {}).get("items", [])
            if not items:
                break

            for item in items:
                bid = item.get("beer", {}).get("bid")
                if bid and bid not in beer_ids:
                    beer_ids.append(bid)

            if len(beer_ids) >= data.get("total_count", 0):
                break
            offset = len(beer_ids)
            time.sleep(self._delay)

        return beer_ids

    def _get_page(self, url: str) -> str | None:
        try:
            response = self._scraper.get(url, timeout=_TIMEOUT)
        except Exception as exc:
            logger.warning("Untappd request failed for %s: %s", url, exc)
            return None
        if response.status_code != 200:
            logger.warning("Untappd returned %s for %s", response.status_code, url)
            return None
        return response.text

    def _inject_cookie(self) -> None:
        if self._cookie_injected or not self._cookie:
            return
        self._scraper.get(f"{UNTAPPD_BASE}/", timeout=_TIMEOUT)
        self._scraper.cookies.set(COOKIE_NAME, self._cookie)
        self._cookie_injected = True

    def _cookie_expired(self, response: Response) -> bool:
        return 'action="login"' in response.text or "/login" in response.url

    def _expired_cookie_error(self, context: str) -> UntappdCookieExpired:
        exc = UntappdCookieExpired("Untappd session cookie has expired")
        sentry_sdk.capture_exception(exc)
        logger.warning("Untappd cookie expired during %s", context)
        return exc

    def _check_cookie(self, response: Response, context: str) -> None:
        if self._cookie_expired(response):
            raise self._expired_cookie_error(context)
