import json

import pytest
import responses
from beers.models import Beer, ExternalAPI, Stock, Store
from beers.tasks import update_stock_from_vmp
from beers.vmp import circuit_breaker
from django.core.management.base import CommandError


def create_query_url(product, store_id, page):
    if "alkoholfritt" in product:
        query = (
            ":name-asc:mainCategory:alkoholfritt:mainSubCategory:"
            + product
            + ":availableInStores:"
            + str(store_id)
        )
    else:
        query = (
            ":name-asc:mainCategory:" + product + ":availableInStores:" + str(store_id)
        )
    req_url = (
        "https://api.test.com/v4/products/search?currentPage="
        + str(page)
        + "&fields=DEFAULT&pageSize=100&q="
        + query
    )
    return req_url


def json_response(product_id, stock):
    if stock == 0:
        data = {
            "products": [],
            "pagination": {"totalPages": 1},
        }
    else:
        data = {
            "products": [
                {
                    "code": product_id,
                    "name": "Test Beer",
                    "url": f"/p/{product_id}",
                    "volume": {"value": 50},
                    "main_category": {"name": "Øl"},
                    "main_country": {"name": "Norge"},
                    "product_selection": "Basisutvalget",
                    "productAvailability": {
                        "storesAvailability": {
                            "infos": [
                                {
                                    "availability": "Lager: " + str(stock),
                                }
                            ]
                        }
                    },
                },
            ],
            "pagination": {"totalPages": 1},
        }
    return json.dumps(data)


@pytest.fixture(autouse=True)
def setup(db):
    ExternalAPI.objects.create(
        name="vinmonopolet_v2",
        baseurl="https://api.test.com/v4/",
    )
    ExternalAPI.objects.create(
        name="vinmonopolet_v3",
        baseurl="https://api.test.com/v4/",
    )
    Store.objects.create(
        store_id=123,
        name="store1",
        address="address1",
        zipcode=1234,
        area="area1",
        category="cat1",
        gps_lat=59.9275692,
        gps_long=10.9583706,
    )
    Store.objects.create(
        store_id=321,
        name="store2",
        address="address2",
        zipcode=4321,
        area="area2",
        category="cat2",
        gps_lat=49.9275692,
        gps_long=10.9583706,
    )
    Beer.objects.create(
        vmp_id=12611502,
        vmp_name="Ayinger Winterbock",
        active=True,
    )
    Beer.objects.create(
        vmp_id=14194601,
        vmp_name="Mold Sider Gaustad",
        active=True,
    )
    Beer.objects.create(
        vmp_id=13863804,
        vmp_name="Mjøderiet Maple Temptation",
        active=True,
    )
    Beer.objects.create(
        vmp_id=11983702,
        vmp_name="Lervig No Worries Alcohol Free IPA",
        active=True,
    )
    Beer.objects.create(
        vmp_id=15697202,
        vmp_name="XO Ingefærøl Alkoholfri",
        active=True,
    )
    Beer.objects.create(
        vmp_id=14439202,
        vmp_name="Edru Harding",
        active=True,
    )


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.mark.django_db
def test_add_stock(mocked_responses):
    stores = Store.objects.all()
    products = [
        "øl",
        "sider",
        "mjød",
        "alkoholfritt_alkoholfritt_øl",
        "alkoholfritt_alkoholfri_ingefærøl",
        "alkoholfritt_alkoholfri_sider",
    ]

    for store in stores:
        for product in products:
            if product == "øl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(12611502, 11),
                    status=200,
                )
            if product == "sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(14194601, 22),
                    status=200,
                )
            if product == "mjød":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(13863804, 33),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfritt_øl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(11983702, 44),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_ingefærøl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(15697202, 55),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(14439202, 66),
                    status=200,
                )

    update_stock_from_vmp(2)

    assert Stock.objects.get(store=123, beer=12611502).quantity == 11
    assert Stock.objects.get(store=123, beer=14194601).quantity == 22
    assert Stock.objects.get(store=123, beer=13863804).quantity == 33
    assert Stock.objects.get(store=123, beer=11983702).quantity == 44
    assert Stock.objects.get(store=123, beer=15697202).quantity == 55
    assert Stock.objects.get(store=123, beer=14439202).quantity == 66
    assert Stock.objects.get(store=321, beer=12611502).quantity == 11
    assert Stock.objects.get(store=321, beer=14194601).quantity == 22
    assert Stock.objects.get(store=321, beer=13863804).quantity == 33
    assert Stock.objects.get(store=321, beer=11983702).quantity == 44
    assert Stock.objects.get(store=321, beer=15697202).quantity == 55
    assert Stock.objects.get(store=321, beer=14439202).quantity == 66


@pytest.mark.django_db
def test_update_and_remove_stock(mocked_responses):
    stores = Store.objects.all()
    products = [
        "øl",
        "sider",
        "mjød",
        "alkoholfritt_alkoholfritt_øl",
        "alkoholfritt_alkoholfri_ingefærøl",
        "alkoholfritt_alkoholfri_sider",
    ]

    # Update and delete stocks
    for store in stores:
        for product in products:
            if product == "øl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(12611502, 22),
                    status=200,
                )
            if product == "sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(14194601, 0),
                    status=200,
                )
            if product == "mjød":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(13863804, 0),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfritt_øl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(11983702, 11),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_ingefærøl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(15697202, 0),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=json_response(14439202, 0),
                    status=200,
                )
    update_stock_from_vmp(2)

    assert Stock.objects.get(store=123, beer=12611502).quantity == 22
    assert Stock.objects.get(store=321, beer=12611502).quantity == 22
    assert Stock.objects.get(store=123, beer=11983702).quantity == 11
    assert Stock.objects.get(store=321, beer=11983702).quantity == 11
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=123, beer=14194601)
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=123, beer=13863804)
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=321, beer=14194601)
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=321, beer=13863804)
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=123, beer=15697202)
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=123, beer=14439202)
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=321, beer=15697202)
    with pytest.raises(Stock.DoesNotExist):
        Stock.objects.get(store=321, beer=14439202)


def paged_body(product_id, stock, total_pages):
    return json.dumps(
        {
            "products": [
                {
                    "code": product_id,
                    "name": "Test Beer",
                    "url": f"/p/{product_id}",
                    "volume": {"value": 50},
                    "main_category": {"name": "Øl"},
                    "main_country": {"name": "Norge"},
                    "product_selection": "Basisutvalget",
                    "productAvailability": {
                        "storesAvailability": {
                            "infos": [{"availability": "Lager: " + str(stock)}]
                        }
                    },
                }
            ],
            "pagination": {"totalPages": total_pages},
        }
    )


@pytest.mark.django_db
def test_budget_pauses_then_resumes(mocked_responses):
    Store.objects.filter(store_id=321).delete()
    sid = 123

    mocked_responses.add(
        responses.GET,
        create_query_url("øl", sid, 0),
        body=paged_body(12611502, 11, 2),
        status=200,
    )
    update_stock_from_vmp(1, max_requests=1)

    store = Store.objects.get(pk=sid)
    assert store.stock_sync_started is not None
    assert store.stock_sync_category == 0
    assert store.stock_sync_page == 1
    assert store.store_stock_updated is None

    mocked_responses.add(
        responses.GET,
        create_query_url("øl", sid, 1),
        body=paged_body(12611502, 11, 2),
        status=200,
    )
    for product, product_id in (
        ("sider", 14194601),
        ("mjød", 13863804),
        ("alkoholfritt_alkoholfritt_øl", 11983702),
        ("alkoholfritt_alkoholfri_ingefærøl", 15697202),
        ("alkoholfritt_alkoholfri_sider", 14439202),
    ):
        mocked_responses.add(
            responses.GET,
            create_query_url(product, sid, 0),
            body=paged_body(product_id, 22, 1),
            status=200,
        )
    update_stock_from_vmp(1, max_requests=20)

    store.refresh_from_db()
    assert store.stock_sync_started is None
    assert store.stock_sync_category == 0
    assert store.stock_sync_page == 0
    assert store.store_stock_updated is not None
    assert Stock.objects.get(store=sid, beer=14439202).quantity == 22


@pytest.mark.django_db
def test_circuit_breaker_open_skips_run(mocked_responses):
    circuit_breaker.open(100)

    update_stock_from_vmp(2)

    assert Stock.objects.count() == 0


@pytest.mark.django_db
def test_block_opens_breaker_and_saves_cursor(mocked_responses):
    Store.objects.filter(store_id=321).delete()
    sid = 123

    mocked_responses.add(
        responses.GET,
        create_query_url("øl", sid, 0),
        json={},
        status=429,
    )

    with pytest.raises(CommandError):
        update_stock_from_vmp(1)

    assert circuit_breaker.is_open() is True
    store = Store.objects.get(pk=sid)
    assert store.stock_sync_started is not None
    assert store.stock_sync_category == 0
    assert store.stock_sync_page == 0
    assert store.store_stock_updated is None


@pytest.mark.django_db
def test_unstock_only_at_completion(mocked_responses):
    Store.objects.filter(store_id=321).delete()
    sid = 123
    store = Store.objects.get(pk=sid)
    stale = Stock.objects.create(
        store=store,
        beer=Beer.objects.get(pk=12611502),
        quantity=9,
        last_seen_in_stock_sync=None,
    )

    mocked_responses.add(
        responses.GET,
        create_query_url("øl", sid, 0),
        body=json_response(12611502, 0),
        status=200,
    )
    for product, product_id in (
        ("sider", 14194601),
        ("mjød", 13863804),
        ("alkoholfritt_alkoholfritt_øl", 11983702),
        ("alkoholfritt_alkoholfri_ingefærøl", 15697202),
        ("alkoholfritt_alkoholfri_sider", 14439202),
    ):
        mocked_responses.add(
            responses.GET,
            create_query_url(product, sid, 0),
            body=paged_body(product_id, 22, 1),
            status=200,
        )
    update_stock_from_vmp(1)

    stale.refresh_from_db()
    assert stale.quantity == 0
    assert stale.unstocked_at is not None
