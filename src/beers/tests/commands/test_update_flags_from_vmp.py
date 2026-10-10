import io
import json
from urllib.parse import unquote

import pytest
import responses
from django.core.management import call_command
from django.core.management.base import CommandError
from requests import PreparedRequest

from beers.models import Beer, ExternalAPI
from beers.tests.factories import BeerFactory
from clients.vmp import circuit_breaker

SEARCH_URL = "https://api.test.com/v2/products/search"


def product(code: int) -> dict:
    return {
        "code": str(code),
        "name": f"Beer {code}",
        "url": f"/p/{code}",
        "volume": {"value": 33},
        "main_category": {"name": "Øl"},
        "main_country": {"name": "Norge"},
    }


def facet_search(
    hits: dict[str, list[int]], echo: bool = True
) -> responses.CallbackResponse:
    def callback(request: PreparedRequest) -> tuple[int, dict, str]:
        query = unquote(request.url or "")
        facet = next(f for f in hits if f":{f}:true" in query)
        body = {
            "products": [product(code) for code in hits[facet]],
            "pagination": {"totalPages": 1},
            "breadcrumbs": [{"facetCode": facet, "facetValueCode": "true"}]
            if echo
            else [],
        }
        return 200, {}, json.dumps(body)

    return responses.add_callback(responses.GET, SEARCH_URL, callback=callback)


def run() -> None:
    call_command(
        "update_flags_from_vmp",
        request_delay_min=0,
        request_delay_max=0,
        stdout=io.StringIO(),
    )


@pytest.fixture(autouse=True)
def setup(db):
    ExternalAPI.objects.create(
        name="vinmonopolet_v2", baseurl="https://api.test.com/v2/"
    )
    ExternalAPI.objects.create(
        name="vinmonopolet_v3", baseurl="https://api.test.com/v3/"
    )


@responses.activate
def test_sets_and_clears_flags() -> None:
    vegan = BeerFactory(vmp_id=1)
    stale = BeerFactory(vmp_id=2, vegan=True, is_new=True)
    new = BeerFactory(vmp_id=3)
    facet_search({"vegan": [1], "newProducts": [3]})

    run()

    assert Beer.objects.get(pk=vegan.pk).vegan is True
    assert Beer.objects.get(pk=stale.pk).vegan is False
    assert Beer.objects.get(pk=stale.pk).is_new is False
    assert Beer.objects.get(pk=new.pk).is_new is True


@responses.activate
def test_ignored_facet_keeps_flags() -> None:
    beer = BeerFactory(vmp_id=2, vegan=True)
    facet_search({"vegan": [1, 2, 3], "newProducts": []}, echo=False)

    with pytest.raises(CommandError):
        run()

    assert Beer.objects.get(pk=beer.pk).vegan is True


@responses.activate
def test_block_opens_circuit_breaker() -> None:
    responses.add(responses.GET, SEARCH_URL, json={}, status=429)

    with pytest.raises(CommandError):
        run()

    assert circuit_breaker.is_open() is True
