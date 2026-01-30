from __future__ import annotations

from beers.models import (
    Badge,
    Beer,
    Country,
    ExternalAPI,
    Option,
    Release,
    Stock,
    Store,
    Tasted,
    VmpNotReleased,
    WrongMatch,
)
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest


@admin.register(Beer)
class BeerAdmin(admin.ModelAdmin):
    list_display = (
        "vmp_name",
        "main_category",
        "untpd_name",
        "vmp_id",
        "untpd_id",
        "rating",
        "checkins",
        "vmp_updated",
        "untpd_updated",
        "created_at",
        "match_manually",
        "active",
    )
    search_fields = (
        "vmp_name",
        "brewery",
        "vmp_id",
        "untpd_id",
        "style",
    )
    ordering = ("-created_at",)
    list_editable = (
        "match_manually",
        "active",
    )


class MatchManually(Beer):
    class Meta:
        proxy = True


@admin.register(MatchManually)
class MatchManuallyAdmin(BeerAdmin):
    list_display = (
        "vmp_name",
        "untpd_name",
        "vmp_id",
        "untpd_id",
        "match_manually",
        "active",
    )
    fields = (
        "vmp_name",
        "untpd_url",
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Beer]:
        return self.model.objects.filter(match_manually=True, active=True)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "store_id", "address", "store_updated")
    search_fields = ("name", "store_id")


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("store", "beer", "quantity", "stock_updated")
    search_fields = ("store__name", "beer__vmp_name")


@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "active",
        "release_date",
    )
    ordering = ("-release_date",)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "iso_code")
    search_fields = ("name", "iso_code")


@admin.register(Tasted)
class TastedAdmin(admin.ModelAdmin):
    list_display = ("user", "beer")
    search_fields = ("user__username", "beer__vmp_name")
    raw_id_fields = ("user", "beer")


admin.site.register(Option)
admin.site.register(Badge)
admin.site.register(ExternalAPI)
admin.site.register(WrongMatch)
admin.site.register(VmpNotReleased)
