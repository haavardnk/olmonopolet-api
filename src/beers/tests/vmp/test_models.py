from beers.vmp.models import (
    SearchResponse,
    VmpProduct,
    VmpProductDetail,
    VmpStore,
)

PRODUCT_JSON = {
    "code": "1234",
    "name": "Hazy IPA",
    "url": "/p/1234",
    "volume": {"value": 50},
    "main_category": {"name": "Øl"},
    "main_country": {"name": "Norge"},
    "main_sub_category": {"name": "India Pale Ale"},
    "product_selection": "Basisutvalget",
    "price": {"value": 79.90},
    "productAvailability": {
        "deliveryAvailability": {"availableForPurchase": True},
        "storesAvailability": {
            "infos": [
                {
                    "readableValue": "Kan bestilles til alle butikker",
                    "availability": "5",
                }
            ]
        },
    },
    "images": [
        {"url": "https://img/1234.jpg", "format": "product", "imageType": "PRIMARY"}
    ],
}

DETAIL_JSON = {
    **PRODUCT_JSON,
    "color": "Gyllen",
    "smell": "Sitrus",
    "taste": "Humle",
    "allergens": "Inneholder gluten",
    "method": "Overgjæret",
    "vintage": 2024,
    "sugar": "< 1 g/l",
    "acid": "5,2",
    "content": {
        "characteristics": [
            {"name": "Fylde", "value": 3},
            {"name": "Bitterhet", "value": 4},
        ],
        "storagePotential": {"formattedValue": "Drikkeklar nå"},
        "ingredients": [{"formattedValue": "Vann, malt, humle"}],
        "isGoodFor": [{"name": "Lyst kjøtt"}, {"name": "Fisk"}],
    },
}

STORE_JSON = {
    "displayName": "Oslo, Aker Brygge",
    "address": {"line1": "Stranden 1", "postalCode": "0250", "town": "Oslo"},
    "geoPoint": {"latitude": 59.9, "longitude": 10.7},
    "assortment": "Stort utvalg",
}

SEARCH_JSON = {
    "products": [PRODUCT_JSON],
    "pagination": {"totalPages": 3},
    "facets": [
        {
            "code": "availableInStores",
            "values": [{"code": "116", "name": "Oslo", "count": 42}],
        }
    ],
}


class TestProduct:
    def test_parses_aliases_and_snake_case(self):
        product = VmpProduct.model_validate(PRODUCT_JSON)

        assert product.code == "1234"
        assert product.main_sub_category is not None
        assert product.main_sub_category.name == "India Pale Ale"
        assert product.price is not None
        assert product.price.value == 79.90
        assert product.product_availability is not None
        assert product.product_availability.delivery_availability is not None
        assert product.product_availability.delivery_availability.available_for_purchase
        stores = product.product_availability.stores_availability
        assert stores is not None
        infos = stores.infos
        assert infos[0].readable_value == "Kan bestilles til alle butikker"
        assert product.images[0].image_type == "PRIMARY"

    def test_optional_fields_default_none(self):
        data = {
            k: v
            for k, v in PRODUCT_JSON.items()
            if k not in ("price", "main_sub_category")
        }
        product = VmpProduct.model_validate(data)

        assert product.price is None
        assert product.main_sub_category is None


class TestProductDetail:
    def test_parses_content(self):
        detail = VmpProductDetail.model_validate(DETAIL_JSON)

        assert detail.color == "Gyllen"
        assert detail.vintage == 2024
        assert detail.content is not None
        names = [c.name for c in detail.content.characteristics]
        assert "Fylde" in names
        assert detail.content.storage_potential is not None
        assert detail.content.storage_potential.formatted_value == "Drikkeklar nå"
        assert detail.content.ingredients[0].formatted_value == "Vann, malt, humle"
        assert [g.name for g in detail.content.is_good_for] == ["Lyst kjøtt", "Fisk"]


class TestStore:
    def test_parses_store(self):
        store = VmpStore.model_validate(STORE_JSON)

        assert store.display_name == "Oslo, Aker Brygge"
        assert store.address.postal_code == "0250"
        assert store.address.town == "Oslo"
        assert store.geo_point.latitude == 59.9
        assert store.assortment == "Stort utvalg"


class TestSearchResponse:
    def test_parses_pagination_and_facets(self):
        response = SearchResponse.model_validate(SEARCH_JSON)

        assert response.pagination.total_pages == 3
        assert len(response.products) == 1
        assert response.facets[0].code == "availableInStores"
        assert response.facets[0].values[0].code == "116"
