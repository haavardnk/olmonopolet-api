from __future__ import annotations

from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from beers.api.serializers.beer import BeerSerializer
from beers.models import Beer, Stock, Store


class StockChangeBeerSerializer(BeerSerializer):
    class Meta:
        model = Beer
        fields = [
            "vmp_id",
            "vmp_name",
            "price",
            "rating",
            "checkins",
            "label_sm_url",
            "main_category",
            "sub_category",
            "style",
            "stock",
            "abv",
            "volume",
            "price_per_volume",
            "vmp_url",
            "untpd_url",
            "untpd_id",
            "country",
            "country_code",
            "user_tasted",
        ]


class StockChangeSerializer(serializers.ModelSerializer):
    beer = StockChangeBeerSerializer()

    class Meta:
        model = Stock
        fields = [
            "store",
            "quantity",
            "stock_updated",
            "stocked_at",
            "unstocked_at",
            "beer",
        ]


class StoreSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = "__all__"


class StockSerializer(serializers.ModelSerializer):
    beer_name = serializers.CharField(read_only=True, source="beer.vmp_name")
    store_name = serializers.CharField(read_only=True, source="store.name")

    class Meta:
        model = Stock
        fields = [
            "beer",
            "beer_name",
            "store",
            "store_name",
            "quantity",
            "stock_updated",
        ]
