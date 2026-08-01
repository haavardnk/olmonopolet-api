from __future__ import annotations

from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from beers.models import Country, Release


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
