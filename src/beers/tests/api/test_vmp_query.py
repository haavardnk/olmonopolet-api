import pytest
from rest_framework.test import APIClient

from beers.api.vmp_query import parse_vmp_query
from beers.models import Beer
from beers.tests.factories import (
    BeerFactory,
    CountryFactory,
    StockFactory,
    StoreFactory,
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "hit", "miss"),
    [
        (":relevance:mainCategory:øl", {"main_category_code": "øl"}, {}),
        (":relevance:mainCategory:sider", {"main_category": "Sider"}, {}),
        (
            ":relevance:mainSubCategory:øl_ipa",
            {"sub_category_code": "øl_ipa"},
            {"sub_category_code": "øl_stout"},
        ),
        (
            ":relevance:mainDistrict:norge_rogaland",
            {"district_code": "norge_rogaland"},
            {"district_code": "norge_oslo"},
        ),
        (":relevance:brand:jåttå", {"producer_code": "jåttå"}, {}),
        (":relevance:price:40", {"price": 59.9}, {"price": 60}),
        (":relevance:price:1000", {"price": 1500}, {"price": 999}),
        (":relevance:priceValue:[100 TO 200]", {"price": 150}, {"price": 201}),
        (":relevance:priceValue:[* TO 50]", {"price": 50}, {"price": 51}),
        (
            ":relevance:litrePrice:181.52",
            {"price": 90.76, "volume": 0.5},
            {"price": 90.76, "volume": 0.33},
        ),
        (":relevance:volumeRanges:20 - 33 cl", {"volume": 0.33}, {"volume": 0.5}),
        (":relevance:volumeRanges:1 - 2,9 liter", {"volume": 1.5}, {"volume": 3}),
        (":relevance:volumeRanges:3 liter og over", {"volume": 5}, {"volume": 2}),
        (":relevance:alcohol:4,8 - 6 %", {"vmp_abv": 5.9}, {"vmp_abv": 6}),
        (":relevance:Sukker:3 - 6 g/l", {"sugar": 6}, {"sugar": 7}),
        (":relevance:Fylde:7-8", {"fullness": 8}, {"fullness": 9}),
        (
            ":relevance:isGoodfor:D",
            {"food_pairing_codes": ["Q", "D"]},
            {"food_pairing_codes": ["Q"]},
        ),
        (":relevance:year:2024", {"year": 2024}, {"year": 2023}),
        (
            ":relevance:Emballasjetype:Metall",
            {"package_material": "Metall"},
            {"package_material": "Glass"},
        ),
        (
            ":relevance:Lagringsgrad:Drikkeklar, ikke egnet for lagring",
            {"storable": "Drikkeklar, ikke egnet for lagring"},
            {"storable": "Drikkeklar nå, men kan også lagres"},
        ),
        (":relevance:Raastoff:Humle", {"raw_materials": "Vann, Humle"}, {}),
        (
            ":relevance:StockAvailability:Bestillingsutvalget",
            {"product_selection": "Bestillingsutvalget"},
            {"product_selection": "Tilleggsutvalget"},
        ),
        (
            ":relevance:StockAvailability:AndreUtvalg",
            {"product_selection": "Basisutvalget"},
            {"product_selection": "Spesialutvalg"},
        ),
        (":relevance:vegan:true", {"vegan": True}, {"vegan": False}),
        (":relevance:newProducts:true", {"is_new": True}, {"is_new": False}),
        (":relevance:Eco:true", {"eco": True}, {"eco": False}),
        (":relevance:Gluten:true", {"gluten_free": True}, {"gluten_free": None}),
        (":relevance:inStock:true", {"post_delivery": True}, {"post_delivery": False}),
        (":relevance:buyableBy18YearOlds:true", {"age_limit": 18}, {"age_limit": 20}),
        (
            ":relevance:Fylde:3-4:Fylde:7-8",
            {"fullness": 4},
            {"fullness": 5},
        ),
        (
            ":relevance:Fylde:7-8:vegan:true",
            {"fullness": 7, "vegan": True},
            {"fullness": 7, "vegan": False},
        ),
        ("pils:relevance", {"vmp_name": "Lys Pils"}, {"vmp_name": "Stout"}),
    ],
)
def test_facet_filters(query: str, hit: dict, miss: dict) -> None:
    matching = BeerFactory(**hit)
    other = BeerFactory(main_category_code="vin", main_category="Vin", **miss)

    pks = set(Beer.objects.filter(parse_vmp_query(query).query).values_list("pk"))

    assert (matching.pk,) in pks
    assert (other.pk,) not in pks


@pytest.mark.django_db
def test_country_matches_code_or_name() -> None:
    norway = BeerFactory(country=CountryFactory(name="Norge"))
    sweden = BeerFactory(country=CountryFactory(name="Sverige", vmp_code="se"))

    by_name = parse_vmp_query(":relevance:mainCountry:norge").query
    by_code = parse_vmp_query(":relevance:mainCountry:se").query

    assert set(Beer.objects.filter(by_name)) == {norway}
    assert set(Beer.objects.filter(by_code)) == {sweden}


@pytest.mark.django_db
def test_store_requires_stock() -> None:
    store = StoreFactory(store_id=162)
    stocked = BeerFactory()
    empty = BeerFactory()
    StockFactory(store=store, beer=stocked, quantity=3)
    StockFactory(store=store, beer=empty, quantity=0)

    query = parse_vmp_query(":relevance:availableInStores:162").query

    assert set(Beer.objects.filter(query)) == {stocked}


@pytest.mark.parametrize(
    ("query", "ignored"),
    [
        (":relevance:mainCategory:øl", []),
        (":relevance:unknownFacet:x:Fylde:7-8", ["unknownFacet"]),
        (":relevance:price:abc", ["price"]),
        (":relevance:vegan:false", ["vegan"]),
        ("", []),
    ],
)
def test_ignored_facets(query: str, ignored: list[str]) -> None:
    assert parse_vmp_query(query).ignored == ignored


@pytest.mark.django_db
def test_list_reports_ignored_facets() -> None:
    beer = BeerFactory(fullness=7)
    BeerFactory(fullness=2)

    response = APIClient().get(
        "/beers/", {"vmp_query": ":relevance:Fylde:7-8:mystery:1"}
    )

    assert [r["vmp_id"] for r in response.data["results"]] == [beer.vmp_id]
    assert response.data["ignored_facets"] == ["mystery"]
