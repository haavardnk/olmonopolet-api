from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True, extra="ignore", coerce_numbers_to_str=True
    )


class Named(_Base):
    name: str


class ValueField(_Base):
    value: float


class StoreInfo(_Base):
    readable_value: str | None = Field(default=None, alias="readableValue")
    availability: str | None = None


class StoresAvailability(_Base):
    infos: list[StoreInfo] = Field(default_factory=list)


class DeliveryAvailability(_Base):
    available_for_purchase: bool | None = Field(
        default=None, alias="availableForPurchase"
    )


class ProductAvailability(_Base):
    stores_availability: StoresAvailability | None = Field(
        default=None, alias="storesAvailability"
    )
    delivery_availability: DeliveryAvailability | None = Field(
        default=None, alias="deliveryAvailability"
    )


class Image(_Base):
    url: str | None = None
    format: str | None = None
    image_type: str | None = Field(default=None, alias="imageType")


class VmpProduct(_Base):
    code: str
    name: str
    url: str
    volume: ValueField
    main_category: Named
    main_country: Named
    product_selection: str
    main_sub_category: Named | None = None
    price: ValueField | None = None
    product_availability: ProductAvailability | None = Field(
        default=None, alias="productAvailability"
    )
    images: list[Image] = Field(default_factory=list)

    @field_validator("main_sub_category", mode="before")
    @classmethod
    def _empty_sub_category_to_none(cls, value: Any) -> Any:
        if isinstance(value, dict) and not value.get("name"):
            return None
        return value


class Characteristic(_Base):
    name: str | None = None
    value: str | int | float | None = None


class StoragePotential(_Base):
    formatted_value: str | None = Field(default=None, alias="formattedValue")


class Ingredient(_Base):
    formatted_value: str | None = Field(default=None, alias="formattedValue")


class Content(_Base):
    characteristics: list[Characteristic] = Field(default_factory=list)
    storage_potential: StoragePotential | None = Field(
        default=None, alias="storagePotential"
    )
    ingredients: list[Ingredient] = Field(default_factory=list)
    is_good_for: list[Named] = Field(default_factory=list, alias="isGoodFor")


class VmpProductDetail(VmpProduct):
    content: Content | None = None
    color: str | None = None
    smell: str | None = None
    taste: str | None = None
    allergens: str | None = None
    method: str | None = None
    vintage: int | None = None
    year: int | None = None
    sugar: str | None = None
    acid: str | None = None


class Address(_Base):
    line1: str | None = None
    postal_code: str | None = Field(default=None, alias="postalCode")
    town: str | None = None


class GeoPoint(_Base):
    latitude: float | None = None
    longitude: float | None = None


class VmpStore(_Base):
    display_name: str = Field(alias="displayName")
    address: Address
    geo_point: GeoPoint = Field(alias="geoPoint")
    code: str | None = None
    assortment: str | None = None


class Pagination(_Base):
    total_pages: int = Field(default=0, alias="totalPages")


class FacetValue(_Base):
    code: str | None = None
    name: str | None = None
    count: int | None = None


class Facet(_Base):
    code: str | None = None
    values: list[FacetValue] = Field(default_factory=list)


class SearchResponse(_Base):
    products: list[VmpProduct] = Field(default_factory=list)
    pagination: Pagination = Field(default_factory=Pagination)
    facets: list[Facet] = Field(default_factory=list)
