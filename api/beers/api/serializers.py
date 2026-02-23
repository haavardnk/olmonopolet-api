from __future__ import annotations

from beers.models import (
    Badge,
    Beer,
    Country,
    Release,
    Stock,
    Store,
    UserList,
    UserListItem,
    WrongMatch,
)
from django.contrib.auth.models import User
from django.db import models
from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from .utils import parse_bool


class BeerSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="beer-detail")
    badges = serializers.SerializerMethodField("get_badges")
    stock = serializers.SerializerMethodField("get_stock")
    all_stock = serializers.SerializerMethodField("get_all_stock")
    country = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )
    country_code = serializers.CharField(
        source="country.iso_code", read_only=True, allow_null=True
    )
    value_score = serializers.FloatField(read_only=True)
    user_tasted = serializers.BooleanField(read_only=True)

    def get_badges(self, beer: Beer):
        badges_queryset = Badge.objects.filter(beer=beer)
        serializer = BadgeSerializer(instance=badges_queryset, many=True)
        return serializer.data

    def get_stock(self, beer: Beer) -> int | None:
        store = self.context["request"].query_params.get("store") or self.context[
            "request"
        ].query_params.get("check_store")
        if store is not None and len(store.split(",")) < 2:
            try:
                stock = Stock.objects.get(beer=beer, store=store)
                return stock.quantity
            except Stock.DoesNotExist:
                return None
        return None

    def get_all_stock(self, beer: Beer):
        all_stock = self.context["request"].query_params.get("all_stock")
        if all_stock and parse_bool(all_stock):
            try:
                stock_queryset = Stock.objects.filter(beer=beer).exclude(quantity=0)
                serializer = AllStockSerializer(instance=stock_queryset, many=True)
                return serializer.data
            except Stock.DoesNotExist:
                return None
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

    def get_beer_count(self, release: Release) -> int:
        return getattr(release, "product_count", 0)

    def get_product_stats(self, release: Release) -> dict[str, int]:
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
            "is_christmas_release",
        ]


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["name", "iso_code"]


class UserListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserListItem
        fields = [
            "id",
            "product_id",
            "quantity",
            "year",
            "notes",
            "sort_order",
            "created_at",
        ]
        read_only_fields = ["id", "sort_order", "created_at"]


class UserListItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserListItem
        fields = ["product_id", "quantity", "year", "notes"]

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1")
        return value


class UserListItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserListItem
        fields = ["quantity", "year", "notes"]

    def validate_quantity(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Quantity must be at least 1")
        return value


class UserListSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()
    product_ids = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = UserList
        fields = [
            "id",
            "name",
            "description",
            "list_type",
            "selected_store_id",
            "event_date",
            "share_token",
            "sort_order",
            "created_at",
            "updated_at",
            "item_count",
            "product_ids",
            "is_past",
            "stats",
            "items",
            "total_price",
        ]
        read_only_fields = [
            "id",
            "share_token",
            "created_at",
            "updated_at",
            "item_count",
            "product_ids",
            "is_past",
            "stats",
            "items",
            "total_price",
        ]

    def get_item_count(self, obj):
        return obj.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    def get_product_ids(self, obj):
        return list(obj.items.values_list("product_id", flat=True))

    def get_is_past(self, obj):
        if obj.list_type != UserList.ListType.EVENT or not obj.event_date:
            return None
        from datetime import date

        return obj.event_date < date.today()

    def get_stats(self, obj):
        if obj.list_type != UserList.ListType.CELLAR:
            return None

        items = obj.items.all()
        if not items.exists():
            return {
                "total_bottles": 0,
                "total_value": 0,
                "oldest_year": None,
                "newest_year": None,
            }

        total_bottles = items.aggregate(total=models.Sum("quantity"))["total"] or 0
        years = items.exclude(year__isnull=True).values_list("year", flat=True)

        total_value = 0
        for item in items:
            try:
                beer = Beer.objects.get(vmp_id=item.product_id)
                if beer.price:
                    total_value += item.quantity * beer.price
            except Beer.DoesNotExist:
                pass

        return {
            "total_bottles": total_bottles,
            "total_value": round(total_value, 2),
            "oldest_year": min(years) if years else None,
            "newest_year": max(years) if years else None,
        }

    def get_items(self, obj):
        if not self.context.get("include_items", False):
            return None
        items = obj.items.all()
        return UserListItemSerializer(
            items, many=True, context={"selected_store_id": obj.selected_store_id}
        ).data

    def get_total_price(self, obj):
        if obj.list_type != UserList.ListType.SHOPPING:
            return None

        total = 0
        for item in obj.items.all():
            try:
                beer = Beer.objects.get(vmp_id=item.product_id)
                if beer.price:
                    total += item.quantity * beer.price
            except Beer.DoesNotExist:
                pass
        return round(total, 2)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("is_past") is None:
            data.pop("is_past", None)
        if data.get("stats") is None:
            data.pop("stats", None)
        if data.get("items") is None:
            data.pop("items", None)
        if data.get("total_price") is None:
            data.pop("total_price", None)
        return data


class UserListCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserList
        fields = [
            "id",
            "name",
            "description",
            "list_type",
            "event_date",
            "sort_order",
            "share_token",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "sort_order",
            "share_token",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        if data.get("list_type") == UserList.ListType.EVENT and not data.get(
            "event_date"
        ):
            pass
        return data


class UserListUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserList
        fields = ["name", "description", "selected_store_id", "event_date", "list_type"]


class SharedUserListSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = UserList
        fields = [
            "id",
            "name",
            "description",
            "list_type",
            "selected_store_id",
            "store_name",
            "event_date",
            "share_token",
            "sort_order",
            "created_at",
            "updated_at",
            "user_name",
            "is_past",
            "stats",
            "items",
            "total_price",
        ]

    def get_items(self, obj):
        items = obj.items.all()
        return UserListItemSerializer(
            items, many=True, context={"selected_store_id": obj.selected_store_id}
        ).data

    def get_user_name(self, obj):
        if obj.user.first_name or obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return obj.user.username

    def get_store_name(self, obj):
        if obj.selected_store_id:
            store = Store.objects.filter(store_id=obj.selected_store_id).first()
            return store.name if store else None
        return None

    def get_is_past(self, obj):
        if obj.list_type != UserList.ListType.EVENT or not obj.event_date:
            return None
        from datetime import date

        return obj.event_date < date.today()

    def get_stats(self, obj):
        if obj.list_type != UserList.ListType.CELLAR:
            return None

        items = obj.items.all()
        if not items.exists():
            return {
                "total_bottles": 0,
                "total_value": 0,
                "oldest_year": None,
                "newest_year": None,
            }

        total_bottles = items.aggregate(total=models.Sum("quantity"))["total"] or 0
        years = items.exclude(year__isnull=True).values_list("year", flat=True)

        total_value = 0
        for item in items:
            try:
                beer = Beer.objects.get(vmp_id=item.product_id)
                if beer.price:
                    total_value += item.quantity * beer.price
            except Beer.DoesNotExist:
                pass

        return {
            "total_bottles": total_bottles,
            "total_value": round(total_value, 2),
            "oldest_year": min(years) if years else None,
            "newest_year": max(years) if years else None,
        }

    def get_total_price(self, obj):
        if obj.list_type != UserList.ListType.SHOPPING:
            return None

        total = 0
        for item in obj.items.all():
            try:
                beer = Beer.objects.get(vmp_id=item.product_id)
                if beer.price:
                    total += item.quantity * beer.price
            except Beer.DoesNotExist:
                pass
        return round(total, 2)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("is_past") is None:
            data.pop("is_past", None)
        if data.get("stats") is None:
            data.pop("stats", None)
        if data.get("total_price") is None:
            data.pop("total_price", None)
        return data


class ListReorderSerializer(serializers.Serializer):
    list_ids = serializers.ListField(child=serializers.IntegerField())


class ItemReorderSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.IntegerField())
