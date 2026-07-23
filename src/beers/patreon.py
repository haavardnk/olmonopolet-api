from __future__ import annotations

import logging
import os
import time

import requests
import sentry_sdk
from beers.models import Option
from django.core.cache import cache

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.patreon.com/api/oauth2/token"
POSTS_URL = "https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/posts"
POSTS_FIELDS = "title,content,url,published_at,is_public"
POSTS_CACHE_KEY = "patreon_posts"
POSTS_CACHE_TTL = 60 * 60
ACCESS_TOKEN_LEEWAY = 60
REQUEST_TIMEOUT = 30


def _option_get(name: str) -> str:
    option = Option.objects.filter(name=name).first()
    return option.value if option else ""


def _option_set(name: str, value: str) -> None:
    Option.objects.update_or_create(
        name=name, defaults={"active": True, "value": value}
    )


def _refresh_access_token() -> str:
    refresh_token = _option_get("patreon_refresh_token") or os.getenv(
        "PATREON_REFRESH_TOKEN", ""
    )
    client_id = os.getenv("PATREON_CLIENT_ID", "")
    client_secret = os.getenv("PATREON_CLIENT_SECRET", "")
    if not (refresh_token and client_id and client_secret):
        return ""

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        logger.warning("Patreon token refresh failed: %s", resp.status_code)
        sentry_sdk.capture_message(f"Patreon token refresh failed: {resp.status_code}")
        return ""

    data = resp.json()
    access_token = data.get("access_token", "")
    new_refresh_token = data.get("refresh_token", "")
    expires_in = data.get("expires_in", 0)
    if new_refresh_token:
        _option_set("patreon_refresh_token", new_refresh_token)
    if access_token:
        expires_at = int(time.time()) + expires_in - ACCESS_TOKEN_LEEWAY
        _option_set("patreon_access_token", access_token)
        _option_set("patreon_access_token_expires", str(expires_at))
    return access_token


def _get_access_token(force: bool = False) -> str:
    if not force:
        access_token = _option_get("patreon_access_token")
        expires = _option_get("patreon_access_token_expires")
        if access_token and expires.isdigit() and int(time.time()) < int(expires):
            return access_token

    refreshed = _refresh_access_token()
    if refreshed:
        return refreshed
    return _option_get("patreon_access_token") or os.getenv("PATREON_ACCESS_TOKEN", "")


def _request_posts(access_token: str, count: int) -> requests.Response:
    campaign_id = os.getenv("PATREON_CAMPAIGN_ID", "")
    return requests.get(
        POSTS_URL.format(campaign_id=campaign_id),
        params={
            "fields[post]": POSTS_FIELDS,
            "page[count]": count,
            "sort": "-published_at",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Olmonopolet - API",
        },
        timeout=REQUEST_TIMEOUT,
    )


def _serialize_posts(raw_posts: list[dict]) -> list[dict]:
    posts = []
    for post in raw_posts:
        attributes = post.get("attributes", {})
        if not attributes.get("is_public"):
            continue
        raw_url = attributes.get("url", "")
        url = (
            raw_url
            if raw_url.startswith("http")
            else f"https://www.patreon.com{raw_url}"
        )
        posts.append(
            {
                "id": post.get("id", ""),
                "title": attributes.get("title"),
                "content": attributes.get("content"),
                "url": url,
                "published_at": attributes.get("published_at"),
                "is_public": True,
            }
        )
    posts.sort(key=lambda post: post["published_at"] or "", reverse=True)
    return posts


def _fetch_from_patreon(count: int) -> list[dict] | None:
    if not os.getenv("PATREON_CAMPAIGN_ID", ""):
        return None

    access_token = _get_access_token()
    if not access_token:
        return None

    resp = _request_posts(access_token, count)
    if resp.status_code == 401:
        access_token = _get_access_token(force=True)
        if not access_token:
            return None
        resp = _request_posts(access_token, count)

    if resp.status_code != 200:
        logger.warning("Patreon posts fetch failed: %s", resp.status_code)
        sentry_sdk.capture_message(f"Patreon posts fetch failed: {resp.status_code}")
        return None

    return _serialize_posts(resp.json().get("data", []))


def fetch_patreon_posts(count: int = 10) -> list[dict]:
    cached = cache.get(POSTS_CACHE_KEY)
    if cached is not None:
        return cached

    posts = _fetch_from_patreon(count)
    if posts is None:
        return []

    cache.set(POSTS_CACHE_KEY, posts, POSTS_CACHE_TTL)
    return posts
