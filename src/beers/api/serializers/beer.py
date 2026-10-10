from __future__ import annotations

from datetime import UTC, datetime

from django.db.models import Count, F, Q
from django.utils.functional import cached_property
from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from beers.api.utils import parse_bool
from beers.models import Badge, Beer, Brewery, Release, Stock

FIRST_SEEN_RELIABLE_FROM = datetime(2021, 1, 1, tzinfo=UTC)
OPT_IN_FIELDS = frozenset({"style_stats", "releases"})


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
    first_seen = serializers.SerializerMethodField()
    style_stats = serializers.SerializerMethodField()
    releases = serializers.SerializerMethodField()

    @cached_property
    def fields(self):
        fields = super().fields
        params = getattr(self.context.get("request"), "query_params", {})
        requested = set((params.get("fields") or "").split(","))
        for name in OPT_IN_FIELDS - requested:
            fields.pop(name, None)
        return fields

    def get_first_seen(self, beer: Beer) -> datetime | None:
        if beer.created_at < FIRST_SEEN_RELIABLE_FROM:
            return None
        return beer.created_at

    def get_style_stats(self, beer: Beer) -> dict[str, int | None] | None:
        if not beer.style:
            return None
        peers = Beer.objects.filter(Q(active=True) | Q(pk=beer.pk), style=beer.style)
        counts = peers.aggregate(
            rated=Count("pk", filter=Q(rating__isnull=False)),
            rated_above=Count("pk", filter=Q(rating__gt=beer.rating or 0)),
            priced=Count("pk", filter=Q(price_per_alcohol_unit__isnull=False)),
            priced_above=Count(
                "pk",
                filter=Q(price_per_alcohol_unit__gt=beer.price_per_alcohol_unit or 0),
            ),
        )
        rank = counts["rated_above"] + 1 if beer.rating is not None else None
        cheaper_than = (
            round(100 * counts["priced_above"] / (counts["priced"] - 1))
            if beer.price_per_alcohol_unit is not None and counts["priced"] > 1
            else None
        )
        return {
            "rank": rank,
            "rated": counts["rated"],
            "cheaper_than": cheaper_than,
            "priced": counts["priced"],
        }

    def get_releases(self, beer: Beer):
        releases = beer.release_set.filter(active=True).order_by(
            F("release_date").desc(nulls_last=True)
        )
        return BeerReleaseSerializer(instance=releases, many=True).data

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
            "package_type",
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
            "first_seen",
            "style_stats",
            "releases",
        ]


class BeerReleaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Release
        fields = ["name", "release_date"]


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
