from __future__ import annotations

import re

import feedparser
import requests as http_requests
from beers.models import (
    Badge,
    Beer,
    Country,
    Release,
    Stock,
    Store,
    UntappdRssFeed,
    UserList,
    UserListItem,
    WrongMatch,
)
from django.contrib.auth.models import User
from django.db import models
from django_q.models import OrmQ, Task
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
        serializer = BadgeSerializer(instance=Badge.objects.filter(beer=beer), many=True)
        return serializer.data

    def get_stock(self, beer: Beer) -> int | None:
        store = self.context["request"].query_params.get("store") or self.context[
            "request"
        ].query_params.get("check_store")
        if store is not None and len(store.split(",")) < 2:
            for s in Stock.objects.filter(beer=beer):
                if str(s.store_id) == store:
                    return s.quantity
            return None
        return None

    def get_all_stock(self, beer: Beer):
        all_stock = self.context["request"].query_params.get("all_stock")
        if all_stock and parse_bool(all_stock):
            stocked = [s for s in Stock.objects.filter(beer=beer) if s.quantity != 0]
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
    untappd_list_id = serializers.IntegerField(
        source="untappd_list.untappd_list_id", read_only=True, default=None
    )
    untappd_username = serializers.CharField(
        source="untappd_list.untappd_username", read_only=True, default=None
    )
    is_read_only = serializers.SerializerMethodField()
    last_synced = serializers.DateTimeField(
        source="untappd_list.last_synced", read_only=True, default=None
    )
    sync_status = serializers.SerializerMethodField()

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
            "untappd_list_id",
            "untappd_username",
            "is_read_only",
            "last_synced",
            "sync_status",
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
            "untappd_list_id",
            "untappd_username",
            "is_read_only",
            "last_synced",
            "sync_status",
        ]

    def get_sync_status(self, obj: UserList) -> str | None:
        if obj.list_type != UserList.ListType.UNTAPPD or not obj.untappd_list:
            return None
        task_id = obj.untappd_list.sync_task_id
        if not task_id:
            return None
        task = Task.objects.filter(id=task_id).first()
        if task:
            return "failed" if not task.success else "success"
        if OrmQ.objects.filter(key=task_id).exists():
            return "queued"
        return "running"

    def _untappd_product_ids(self, obj) -> list[str] | None:
        if obj.list_type != UserList.ListType.UNTAPPD or not obj.untappd_list:
            return None
        beer_ids = obj.untappd_list.untappd_beer_ids or []
        if not beer_ids:
            return []
        matched = dict(
            Beer.objects.filter(untpd_id__in=beer_ids).values_list(
                "untpd_id", "vmp_id"
            )
        )
        seen: set[str] = set()
        result: list[str] = []
        for bid in beer_ids:
            vmp_id = matched.get(bid)
            if vmp_id is not None:
                pid = str(vmp_id)
                if pid not in seen:
                    seen.add(pid)
                    result.append(pid)
        return result

    def get_item_count(self, obj):
        untappd_ids = self._untappd_product_ids(obj)
        if untappd_ids is not None:
            return len(untappd_ids)
        return obj.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    def get_product_ids(self, obj):
        untappd_ids = self._untappd_product_ids(obj)
        if untappd_ids is not None:
            return untappd_ids
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

        product_ids = [item.product_id for item in items]
        prices = dict(
            Beer.objects.filter(vmp_id__in=product_ids).values_list("vmp_id", "price")
        )
        total_value = sum(
            item.quantity * (prices.get(item.product_id) or 0) for item in items
        )

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

        items = list(obj.items.all())
        product_ids = [item.product_id for item in items]
        prices = dict(
            Beer.objects.filter(vmp_id__in=product_ids).values_list("vmp_id", "price")
        )
        total = sum(
            item.quantity * (prices.get(item.product_id) or 0) for item in items
        )
        return round(total, 2)

    def get_is_read_only(self, obj) -> bool:
        return obj.list_type == UserList.ListType.UNTAPPD

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
        if data.get("untappd_list_id") is None:
            data.pop("untappd_list_id", None)
            data.pop("untappd_username", None)
            data.pop("last_synced", None)
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

    def validate(self, attrs):
        if attrs.get("list_type") == UserList.ListType.EVENT and not attrs.get(
            "event_date"
        ):
            pass
        return attrs


class UserListUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserList
        fields = ["name", "description", "selected_store_id", "event_date", "list_type"]


class SharedUserListSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()
    product_ids = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    untappd_list_id = serializers.IntegerField(
        source="untappd_list.untappd_list_id", read_only=True, default=None
    )
    untappd_username = serializers.CharField(
        source="untappd_list.untappd_username", read_only=True, default=None
    )
    is_read_only = serializers.SerializerMethodField()
    last_synced = serializers.DateTimeField(
        source="untappd_list.last_synced", read_only=True, default=None
    )

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
            "item_count",
            "product_ids",
            "is_past",
            "stats",
            "items",
            "total_price",
            "untappd_list_id",
            "untappd_username",
            "is_read_only",
            "last_synced",
        ]

    def _untappd_product_ids(self, obj) -> list[str] | None:
        if obj.list_type != UserList.ListType.UNTAPPD or not obj.untappd_list:
            return None
        beer_ids = obj.untappd_list.untappd_beer_ids or []
        if not beer_ids:
            return []
        matched = dict(
            Beer.objects.filter(untpd_id__in=beer_ids).values_list(
                "untpd_id", "vmp_id"
            )
        )
        seen: set[str] = set()
        result: list[str] = []
        for bid in beer_ids:
            vmp_id = matched.get(bid)
            if vmp_id is not None:
                pid = str(vmp_id)
                if pid not in seen:
                    seen.add(pid)
                    result.append(pid)
        return result

    def get_item_count(self, obj):
        untappd_ids = self._untappd_product_ids(obj)
        if untappd_ids is not None:
            return len(untappd_ids)
        return obj.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    def get_product_ids(self, obj):
        untappd_ids = self._untappd_product_ids(obj)
        if untappd_ids is not None:
            return untappd_ids
        return list(obj.items.values_list("product_id", flat=True))

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

        product_ids = [item.product_id for item in items]
        prices = dict(
            Beer.objects.filter(vmp_id__in=product_ids).values_list("vmp_id", "price")
        )
        total_value = sum(
            item.quantity * (prices.get(item.product_id) or 0) for item in items
        )

        return {
            "total_bottles": total_bottles,
            "total_value": round(total_value, 2),
            "oldest_year": min(years) if years else None,
            "newest_year": max(years) if years else None,
        }

    def get_total_price(self, obj):
        if obj.list_type != UserList.ListType.SHOPPING:
            return None

        items = list(obj.items.all())
        product_ids = [item.product_id for item in items]
        prices = dict(
            Beer.objects.filter(vmp_id__in=product_ids).values_list("vmp_id", "price")
        )
        total = sum(
            item.quantity * (prices.get(item.product_id) or 0) for item in items
        )
        return round(total, 2)

    def get_is_read_only(self, obj) -> bool:
        return obj.list_type == UserList.ListType.UNTAPPD

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("is_past") is None:
            data.pop("is_past", None)
        if data.get("stats") is None:
            data.pop("stats", None)
        if data.get("total_price") is None:
            data.pop("total_price", None)
        if data.get("untappd_list_id") is None:
            data.pop("untappd_list_id", None)
            data.pop("untappd_username", None)
            data.pop("last_synced", None)
        return data


class UntappdListSearchResultSerializer(serializers.Serializer):
    list_id = serializers.IntegerField()
    name = serializers.CharField()
    item_count = serializers.IntegerField()


class UntappdListSubscribeSerializer(serializers.Serializer):
    untappd_list_id = serializers.IntegerField()
    untappd_username = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=200)


class ListReorderSerializer(serializers.Serializer):
    list_ids = serializers.ListField(child=serializers.IntegerField())


class ItemReorderSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.IntegerField())


class UntappdRssFeedSerializer(serializers.ModelSerializer):
    class Meta:
        model = UntappdRssFeed
        fields = ["feed_url", "last_synced", "active", "created_at"]
        read_only_fields = ["last_synced", "created_at"]

    def validate_feed_url(self, value: str) -> str:
        if "untappd.com/rss/user/" not in value:
            raise serializers.ValidationError(
                "URL må være en Untappd RSS-feed (https://untappd.com/rss/user/...)"
            )
        match = re.search(r"untappd\.com/rss/user/([^?/]+)", value)
        if not match:
            raise serializers.ValidationError("Kunne ikke hente brukernavn fra RSS-URL")
        if "key=" not in value:
            raise serializers.ValidationError(
                "RSS-URL mangler nøkkelparameter. Bruk den fullstendige URLen fra Untappd RSS-innstillinger."
            )
        username = match.group(1)
        try:
            resp = http_requests.get(
                f"https://untappd.com/user/{username}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
                allow_redirects=True,
            )
            if (
                resp.status_code == 404
                or "set their account to be private" in resp.text
            ):
                raise serializers.ValidationError(
                    "Untappd-profilen er privat. Sett profilen til offentlig for å bruke RSS-synkronisering."
                )
        except serializers.ValidationError:
            raise
        except Exception:
            pass
        try:
            parsed = feedparser.parse(value)
            if parsed.bozo and not parsed.entries:
                raise serializers.ValidationError(
                    "RSS-feeden kunne ikke lastes. Kontroller at URLen er riktig."
                )
        except serializers.ValidationError:
            raise
        except Exception:
            pass
        return value
