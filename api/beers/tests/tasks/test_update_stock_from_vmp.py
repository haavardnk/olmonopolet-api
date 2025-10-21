import pytest
import responses
import xmltodict
from beers.models import Beer, ExternalAPI, Stock, Store
from beers.tasks import update_stock_from_vmp


def create_query_url(product, store_id, page):
    if "alkoholfritt" in product:
        query = (
            ":name-asc:visibleInSearch:true:mainCategory:alkoholfritt:mainSubCategory:"
            + product
            + ":availableInStores:"
            + str(store_id)
            + ":"
        )
    else:
        query = (
            ":name-asc:visibleInSearch:true:mainCategory:"
            + product
            + ":availableInStores:"
            + str(store_id)
            + ":"
        )
    req_url = (
        "https://api.test.com/v4/products/search/?currentPage="
        + str(page)
        + "&fields=FULL&pageSize=100&query="
        + query
    )
    return req_url


def xml_response(product_id, stock):
    if stock == 0:
        xml = xmltodict.unparse(
            {
                "productCategorySearchPage": {
                    "products": [],
                    "pagination": {"totalPages": 1},
                },
            }
        )
    else:
        xml = xmltodict.unparse(
            {
                "productCategorySearchPage": {
                    "products": [
                        {
                            "code": product_id,
                            "productAvailability": {
                                "storesAvailability": {
                                    "infos": {
                                        "availability": "Lager: " + str(stock),
                                    }
                                }
                            },
                        },
                        {},
                    ],
                    "pagination": {"totalPages": 1},
                },
            }
        )
    return xml


@pytest.fixture(autouse=True)
def setup(db):
    ExternalAPI.objects.create(
        name="vinmonopolet",
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
    """
    Test that stock gets added correctly
    """
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
                    body=xml_response(12611502, 11),
                    status=200,
                )
            if product == "sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(14194601, 22),
                    status=200,
                )
            if product == "mjød":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(13863804, 33),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfritt_øl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(11983702, 44),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_ingefærøl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(15697202, 55),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(14439202, 66),
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
    """
    Test that stock gets updated and removed correctly
    """
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
                    body=xml_response(12611502, 22),
                    status=200,
                )
            if product == "sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(14194601, 0),
                    status=200,
                )
            if product == "mjød":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(13863804, 0),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfritt_øl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(11983702, 11),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_ingefærøl":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(15697202, 0),
                    status=200,
                )
            if product == "alkoholfritt_alkoholfri_sider":
                mocked_responses.add(
                    responses.GET,
                    create_query_url(product, store.store_id, 0),
                    body=xml_response(14439202, 0),
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
