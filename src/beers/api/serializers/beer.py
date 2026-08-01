from __future__ import annotations

from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from beers.api.utils import parse_bool
from beers.models import Badge, Beer, Brewery, Stock


class BrewerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Brewery
        fields = ["id", "name", "untpd_url", "label_url", "description"]


class BeerSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="beer-detail")
    badges = serializers.SerializerMethodField("get_badges")
    stock = serializers.SerializerMethodField("get_stock")
    all_stock = serializers.SerializerMethodField("get_all_stock")
    brewery = serializers.CharField(
        source="brewery.name", read_only=True, allow_null=True
    )
    brewery_details = BrewerySerializer(source="brewery", read_only=True)
    country = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )
    country_code = serializers.CharField(
        source="country.iso_code", read_only=True, allow_null=True
    )
    value_score = serializers.FloatField(read_only=True)
    user_tasted = serializers.BooleanField(read_only=True)

    def get_badges(self, beer: Beer):
        return BadgeSerializer(instance=beer.badge_set.all(), many=True).data

    def get_stock(self, beer: Beer) -> int | None:
        store = self.context["request"].query_params.get("store") or self.context[
            "request"
        ].query_params.get("check_store")
        if store is not None and "," not in store:
            for s in beer.stock_set.all():
                if str(s.store_id) == store:
                    return s.quantity
            return None
        return None

    def get_all_stock(self, beer: Beer):
        all_stock = self.context["request"].query_params.get("all_stock")
        if all_stock and parse_bool(all_stock):
            stocked = [s for s in beer.stock_set.all() if s.quantity != 0]
            return AllStockSerializer(instance=stocked, many=True).data
        return None

    class Meta:
        model = Beer
        fields = [
            "url",
            "vmp_id",
            "untpd_id",
            "vmp_name",
            "untpd_name",
            "brewery",
            "brewery_details",
            "vmp_brewery",
            "country",
            "country_code",
            "product_selection",
            "price",
            "volume",
            "price_per_volume",
            "abv",
            "ibu",
            "alcohol_units",
            "price_per_alcohol_unit",
            "rating",
            "checkins",
            "main_category",
            "sub_category",
            "style",
            "description",
            "prioritize_recheck",
            "verified_match",
            "vmp_url",
            "untpd_url",
            "label_hd_url",
            "label_sm_url",
            "vmp_updated",
            "untpd_updated",
            "created_at",
            "badges",
            "stock",
            "all_stock",
            "post_delivery",
            "store_delivery",
            "year",
            "fullness",
            "sweetness",
            "freshness",
            "bitterness",
            "sugar",
            "acid",
            "color",
            "aroma",
            "taste",
            "storable",
            "food_pairing",
            "raw_materials",
            "method",
            "allergens",
            "is_christmas_beer",
            "value_score",
            "user_tasted",
        ]


class AllStockSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(read_only=True, source="store.name")
    gps_lat = serializers.FloatField(read_only=True, source="store.gps_lat")
    gps_long = serializers.FloatField(read_only=True, source="store.gps_long")

    class Meta:
        model = Stock
        fields = ["store_name", "quantity", "gps_lat", "gps_long"]


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = ["text"]
