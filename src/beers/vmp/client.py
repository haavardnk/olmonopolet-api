from __future__ import annotations

import json
import random
import time
from collections.abc import Iterator

from curl_cffi import requests as cffi
from curl_cffi.requests import Response
from curl_cffi.requests.exceptions import RequestException
from django.conf import settings

from beers.models import ExternalAPI
from beers.vmp import circuit_breaker
from beers.vmp.models import (
    FacetValue,
    SearchResponse,
    VmpProduct,
    VmpProductDetail,
    VmpStore,
)

_HEADERS = {"Accept": "application/json"}
_TIMEOUT = 30
_RETRIES = 3
_STORE_FACET = "availableInStores"
_SEARCH_FIELDS = "DEFAULT"
_DEFAULT_DELAY = (1.0, 3.0)
_IMPERSONATE = "chrome"
_BLOCK_STATUSES = frozenset({403, 429, 503})


class VmpBlockedError(Exception):
    pass


class VmpApiError(Exception):
    pass


def _new_session() -> cffi.Session:
    proxy: str | None = settings.VMP_PROXY
    return cffi.Session(
        impersonate=_IMPERSONATE,
        headers=_HEADERS,
        proxy=proxy,
        timeout=_TIMEOUT,
    )


class VmpClient:
    def __init__(
        self,
        v2_baseurl: str,
        v3_baseurl: str,
        request_delay: tuple[float, float] | None = None,
    ) -> None:
        self._v2 = v2_baseurl
        self._v3 = v3_baseurl
        self._delay = request_delay or _DEFAULT_DELAY
        self._session = _new_session()

    @classmethod
    def from_external_api(
        cls, request_delay: tuple[float, float] | None = None
    ) -> VmpClient:
        try:
            v2 = ExternalAPI.objects.get(name="vinmonopolet_v2").baseurl
            v3 = ExternalAPI.objects.get(name="vinmonopolet_v3").baseurl
        except ExternalAPI.DoesNotExist as exc:
            raise VmpApiError(
                "vinmonopolet external API configuration not found"
            ) from exc
        return cls(v2, v3, request_delay)

    def search(
        self,
        category: str,
        sub_category: str | None = None,
        store_id: int | None = None,
        page: int = 0,
        page_size: int = 100,
        sort: str = "name-asc",
    ) -> SearchResponse:
        url = self.search_url(category, sub_category, store_id, page, page_size, sort)
        return SearchResponse.model_validate(self._fetch(url))

    def search_url(
        self,
        category: str,
        sub_category: str | None = None,
        store_id: int | None = None,
        page: int = 0,
        page_size: int = 100,
        sort: str = "name-asc",
    ) -> str:
        query = self._build_query(category, sub_category, store_id, sort)
        return (
            f"{self._v2}products/search?currentPage={page}"
            f"&fields={_SEARCH_FIELDS}&pageSize={page_size}&q={query}"
        )

    def probe(self, url: str) -> tuple[int | None, str, int, str]:
        response = self._get(url)
        if response is None:
            return None, "", 0, ""
        return (
            response.status_code,
            response.headers.get("content-type", ""),
            len(response.text),
            response.text[:300],
        )

    def iter_products(
        self,
        category: str,
        sub_category: str | None = None,
        store_id: int | None = None,
        page_size: int = 100,
        sort: str = "name-asc",
    ) -> Iterator[VmpProduct]:
        first = self.search(category, sub_category, store_id, 0, page_size, sort)
        yield from first.products

        for page in range(1, first.pagination.total_pages):
            response = self.search(
                category, sub_category, store_id, page, page_size, sort
            )
            yield from response.products

    def get_product(self, code: int | str) -> VmpProductDetail:
        url = f"{self._v3}products/{code}?fields=FULL"
        return VmpProductDetail.model_validate(self._fetch(url))

    def get_store(self, code: str) -> VmpStore:
        url = f"{self._v2}stores/{code}"
        return VmpStore.model_validate(self._fetch(url))

    def iter_store_facets(self) -> list[FacetValue]:
        url = f"{self._v2}products/search?currentPage=0&fields=FULL&pageSize=1&q="
        response = SearchResponse.model_validate(self._fetch(url))
        for facet in response.facets:
            if facet.code == _STORE_FACET:
                return facet.values
        raise VmpApiError(f"no '{_STORE_FACET}' facet in vinmonopolet response")

    def barcode_search(self, gtin: str) -> str | None:
        url = f"{self._v2}products/barCodeSearch/{gtin}"
        if circuit_breaker.is_open():
            raise VmpBlockedError("vinmonopolet circuit breaker open")
        for attempt in range(_RETRIES):
            self._sleep(random.uniform(*self._delay))
            response = self._get(url)
            if response is None:
                self._sleep(2**attempt)
                continue
            if response.status_code in _BLOCK_STATUSES:
                circuit_breaker.open()
                raise VmpBlockedError(
                    f"blocked by vinmonopolet (HTTP {response.status_code}) ({url})"
                )
            if response.status_code in (400, 404):
                return None
            if not response.ok:
                self._sleep(2**attempt)
                continue
            try:
                code = response.json().get("code")
            except json.JSONDecodeError:
                self._sleep(2**attempt)
                continue
            return str(code) if code else None
        raise VmpApiError(f"no valid response from vinmonopolet for barcode {gtin}")

    def _build_query(
        self,
        category: str,
        sub_category: str | None,
        store_id: int | None,
        sort: str,
    ) -> str:
        query = f":{sort}:mainCategory:{category}"
        if sub_category:
            query += f":mainSubCategory:{sub_category}"
        if store_id is not None:
            query += f":availableInStores:{store_id}"
        return query

    def _fetch(self, url: str) -> dict:
        if circuit_breaker.is_open():
            raise VmpBlockedError("vinmonopolet circuit breaker open")
        for attempt in range(_RETRIES):
            self._sleep(random.uniform(*self._delay))
            response = self._get(url)
            if response is not None:
                if response.status_code in _BLOCK_STATUSES:
                    circuit_breaker.open()
                    raise VmpBlockedError(
                        f"blocked by vinmonopolet (HTTP {response.status_code}) ({url})"
                    )
                if response.ok:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        pass
            self._session = _new_session()
            self._sleep(2**attempt + random.uniform(0, 1))
        raise VmpApiError(f"no valid JSON response from vinmonopolet ({url})")

    def _get(self, url: str) -> Response | None:
        try:
            return self._session.get(url)
        except RequestException:
            return None

    def _sleep(self, seconds: float) -> None:
        if not settings.TESTING:
            time.sleep(seconds)
