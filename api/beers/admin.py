from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Count, QuerySet
from django.http import HttpRequest

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
    UserList,
    UserListItem,
    VmpNotReleased,
    WrongMatch,
)


class MatchManually(Beer):
    class Meta:
        proxy = True


class UserWithTasted(User):
    class Meta:
        proxy = True
        verbose_name = "User Tasted"
        verbose_name_plural = "User Tasteds"


class UserWithLists(User):
    class Meta:
        proxy = True
        verbose_name = "User List"
        verbose_name_plural = "User Lists"


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


class UserListItemInline(admin.TabularInline):
    model = UserListItem
    extra = 0
    fields = ("product_id", "beer_name", "position", "added_at")
    readonly_fields = ("beer_name", "added_at")
    ordering = ("position",)

    def beer_name(self, obj):
        try:
            beer = Beer.objects.get(vmp_id=obj.product_id)
            return beer.vmp_name
        except Beer.DoesNotExist:
            return f"Unknown ({obj.product_id})"

    beer_name.short_description = "Beer"


class UserListInline(admin.TabularInline):
    model = UserList
    extra = 0
    fields = ("name", "item_count", "sort_order", "share_token")
    readonly_fields = ("share_token", "item_count")
    show_change_link = True

    def item_count(self, obj):
        return obj.items.count()

    item_count.short_description = "Items"

    def has_add_permission(self, request, obj=None):
        return False


class UserListAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "item_count", "sort_order", "created_at")
    list_filter = ("user",)
    search_fields = ("name", "user__username")
    fields = (
        "user",
        "name",
        "description",
        "sort_order",
        "share_token",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("user", "share_token", "created_at", "updated_at")
    inlines = [UserListItemInline]

    def item_count(self, obj):
        return obj.items.count()

    item_count.short_description = "Items"

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


admin.site.register(UserList, UserListAdmin)


@admin.register(UserWithLists)
class UserWithListsAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "list_count")
    search_fields = ("username", "email")
    fields = ("username", "email")
    readonly_fields = ("username", "email")
    inlines = [UserListInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(list_count=Count("lists")).filter(list_count__gt=0)

    @admin.display(ordering="list_count")
    def list_count(self, obj):
        return obj.list_count

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Badge)
admin.site.register(ExternalAPI)
admin.site.register(Option)
admin.site.register(VmpNotReleased)
admin.site.register(WrongMatch)
