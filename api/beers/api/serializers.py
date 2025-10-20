from beers.models import Badge, Beer, Release, Stock, Store, WrongMatch
from django.contrib.auth.models import User
from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from .utils import parse_bool


class BeerSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="beer-detail")
    badges = serializers.SerializerMethodField("get_badges")
    stock = serializers.SerializerMethodField("get_stock")
    all_stock = serializers.SerializerMethodField("get_all_stock")

    def get_badges(self, beer):
        ci = Badge.objects.filter(beer=beer)
        serializer = BadgeSerializer(instance=ci, many=True)
        return serializer.data

    def get_stock(self, beer):
        store = self.context["request"].query_params.get("store")
        if store is not None and len(store.split(",")) < 2:
            try:
                ci = Stock.objects.get(beer=beer, store=store)
            except Stock.DoesNotExist:
                return None
        else:
            return None
        return ci.quantity

    def get_all_stock(self, beer):
        all_stock = self.context["request"].query_params.get("all_stock")
        if all_stock and parse_bool(all_stock):
            try:
                ci = Stock.objects.filter(beer=beer).exclude(quantity=0)
                serializer = AllStockSerializer(instance=ci, many=True)
            except Stock.DoesNotExist:
                return None
        else:
            return None
        return serializer.data

    class Meta:
        model = Beer
        fields = [
            "url",
            "vmp_id",
            "untpd_id",
            "vmp_name",
            "untpd_name",
            "brewery",
            "country",
            "product_selection",
            "price",
            "volume",
            "price_per_volume",
            "abv",
            "ibu",
            "alcohol_units",
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
        ]


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


class AllStockSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(read_only=True, source="store.name")

    class Meta:
        model = Stock
        fields = ["store_name", "quantity"]


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = ["text"]


class AppRatingSerializer(serializers.ModelSerializer):
    rating = serializers.FloatField()
    count = serializers.IntegerField()

    class Meta:
        model = User
        fields = ["rating", "count"]


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


class WrongMatchSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="wrongmatch-detail")
    beer_name = serializers.CharField(read_only=True, source="beer.vmp_name")
    current_untpd_url = serializers.CharField(read_only=True, source="beer.untpd_url")
    current_untpd_id = serializers.CharField(read_only=True, source="beer.untpd_id")

    class Meta:
        model = WrongMatch
        fields = [
            "url",
            "beer",
            "beer_name",
            "current_untpd_url",
            "current_untpd_id",
            "suggested_url",
        ]


class ReleaseSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    beer_count = serializers.SerializerMethodField()
    product_stats = serializers.SerializerMethodField()
    product_selections = serializers.ListField(read_only=True)

    def get_beer_count(self, release):
        # Set beer_count to product_count for compatibility
        return getattr(release, "product_count", 0)

    def get_product_stats(self, release):
        return {
            "product_count": getattr(release, "product_count", 0),
            "beer_count": getattr(release, "beer_count", 0),
            "cider_count": getattr(release, "cider_count", 0),
            "mead_count": getattr(release, "mead_count", 0),
        }

    class Meta:
        model = Release
        fields = [
            "name",
            "active",
            "release_date",
            "beer_count",
            "product_stats",
            "product_selection",
            "product_selections",
            "beer",
        ]
