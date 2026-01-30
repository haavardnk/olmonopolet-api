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
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Count, QuerySet
from django.http import HttpRequest


class MatchManually(Beer):
    class Meta:
        proxy = True


class UserWithTasted(User):
    class Meta:
        proxy = True
        verbose_name = "User Tasted"
        verbose_name_plural = "User Tasteds"


class TastedInline(admin.TabularInline):
    model = Tasted
    extra = 0
    fields = ("beer", "rating")
    readonly_fields = ("beer",)
    raw_id_fields = ("beer",)

    def has_add_permission(self, request, obj=None):
        return False


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
    list_editable = ("match_manually", "active")
    ordering = ("-created_at",)
    search_fields = ("vmp_name", "brewery", "vmp_id", "untpd_id", "style")


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
    fields = ("vmp_name", "untpd_url")

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
    list_display = ("name", "active", "release_date")
    ordering = ("-release_date",)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "iso_code")
    search_fields = ("name", "iso_code")


admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    pass


@admin.register(UserWithTasted)
class UserWithTastedAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "tasted_count")
    search_fields = ("username", "email")
    fields = ("username", "email")
    readonly_fields = ("username", "email")
    inlines = [TastedInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(tasted_count=Count("tasted")).filter(tasted_count__gt=0)

    @admin.display(ordering="tasted_count")
    def tasted_count(self, obj):
        return obj.tasted_count

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Badge)
admin.site.register(ExternalAPI)
admin.site.register(Option)
admin.site.register(VmpNotReleased)
admin.site.register(WrongMatch)
