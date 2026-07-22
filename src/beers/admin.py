from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Count, QuerySet
from django.db.models.functions import Cast
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from beers.models import (
    Badge,
    Beer,
    Brewery,
    Country,
    ExternalAPI,
    Option,
    Release,
    Stock,
    Store,
    Tasted,
    UntappdCheckin,
    UntappdList,
    UntappdRssFeed,
    FollowedList,
    UserList,
    UserListItem,
    VmpCrawlState,
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


class UserWithCheckins(User):
    class Meta:
        proxy = True
        verbose_name = "User Checkin"
        verbose_name_plural = "User Checkins"


class TastedInline(admin.TabularInline):
    model = Tasted
    extra = 0
    fields = ("beer",)
    readonly_fields = ("beer",)
    raw_id_fields = ("beer",)


class BeerBreweryInline(admin.TabularInline):
    model = Beer
    fk_name = "brewery"
    extra = 0
    can_delete = False
    fields = ("label_sm_preview", "vmp_name", "untpd_name", "rating")
    readonly_fields = ("label_sm_preview", "vmp_name", "untpd_name", "rating")
    show_change_link = True

    def has_add_permission(
        self, request: HttpRequest, obj: Brewery | None = None
    ) -> bool:
        return False

    @admin.display(description="Logo")
    def label_sm_preview(self, obj: Beer) -> str:
        if not obj.label_sm_url:
            return "\u2014"
        return format_html('<img src="{}" style="height:40px;" />', obj.label_sm_url)


@admin.register(Beer)
class BeerAdmin(admin.ModelAdmin):
    list_display = (
        "vmp_name",
        "main_category",
        "untpd_name",
        "label_preview",
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
    readonly_fields = ("label_preview",)
    search_fields = (
        "vmp_name",
        "brewery__name",
        "vmp_brewery",
        "vmp_id",
        "untpd_id",
        "style",
    )

    @admin.display(description="Label")
    def label_preview(self, obj: Beer) -> str:
        if not obj.label_hd_url:
            return "\u2014"
        return format_html('<img src="{}" style="height:40px;" />', obj.label_hd_url)


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


@admin.register(Brewery)
class BreweryAdmin(admin.ModelAdmin):
    list_display = ("name", "untpd_url", "logo_preview", "untpd_updated")
    search_fields = ("name", "untpd_url")
    ordering = ("name",)
    inlines = (BeerBreweryInline,)
    readonly_fields = ("logo_preview",)

    @admin.display(description="Logo")
    def logo_preview(self, obj: Brewery) -> str:
        if not obj.label_url:
            return "\u2014"
        return format_html('<img src="{}" style="height:40px;" />', obj.label_url)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "store_id", "address", "store_updated")
    search_fields = ("name", "store_id")


@admin.register(VmpCrawlState)
class VmpCrawlStateAdmin(admin.ModelAdmin):
    list_display = ("scope", "category", "page", "started")


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("store", "beer", "quantity", "stock_updated")
    search_fields = ("store__name", "beer__vmp_name")


class ReleaseBeerInline(admin.TabularInline):
    model = Release.beer.through
    extra = 0
    can_delete = False
    fields = ("label_sm_preview", "beer_link", "beer_rating")
    readonly_fields = ("label_sm_preview", "beer_link", "beer_rating")
    verbose_name = "Beer"
    verbose_name_plural = "Beers"

    def has_add_permission(
        self, request: HttpRequest, obj: Release | None = None
    ) -> bool:
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).select_related("beer")

    @admin.display(description="Logo")
    def label_sm_preview(self, obj) -> str:
        if not obj.beer.label_sm_url:
            return "\u2014"
        return format_html(
            '<img src="{}" style="height:40px;" />', obj.beer.label_sm_url
        )

    @admin.display(description="Beer")
    def beer_link(self, obj) -> str:
        url = reverse("admin:beers_beer_change", args=[obj.beer.pk])
        name = obj.beer.vmp_name or obj.beer.untpd_name or obj.beer.pk
        return format_html('<a href="{}">{}</a>', url, name)

    @admin.display(description="Rating")
    def beer_rating(self, obj):
        return obj.beer.rating


@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "release_date", "beer_count")
    ordering = ("-release_date",)
    exclude = ("beer",)
    inlines = (ReleaseBeerInline,)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Release]:
        return super().get_queryset(request).annotate(_beer_count=Count("beer"))

    @admin.display(description="Beers", ordering="_beer_count")
    def beer_count(self, obj: Release) -> int:
        return obj._beer_count


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
    actions = ["delete_all_tasteds"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.action(description="Delete all tasteds for selected users")
    def delete_all_tasteds(self, request, queryset):
        count, _ = Tasted.objects.filter(user__in=queryset).delete()
        self.message_user(request, f"Deleted {count} tasteds.")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(tasted_count=Count("tasted")).filter(tasted_count__gt=0)

    @admin.display(ordering="tasted_count")
    def tasted_count(self, obj):
        return obj.tasted_count


class UserListItemInline(admin.TabularInline):
    model = UserListItem
    extra = 0
    fields = ("product_id", "beer_name", "quantity", "sort_order", "created_at")
    readonly_fields = ("beer_name", "created_at")
    ordering = ("sort_order",)

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        qs = super().get_queryset(request)
        return qs.annotate(
            _beer_name=models.Subquery(
                Beer.objects.filter(
                    vmp_id=Cast(models.OuterRef("product_id"), models.BigIntegerField())
                ).values("vmp_name")[:1]
            )
        )

    @admin.display(description="Beer")
    def beer_name(self, obj):
        return getattr(obj, "_beer_name", None) or f"Unknown ({obj.product_id})"


class UserListInline(admin.TabularInline):
    model = UserList
    extra = 0
    fields = ("name", "item_count", "sort_order", "share_token")
    readonly_fields = ("share_token", "item_count")
    show_change_link = True

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()


class UserListAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "list_type",
        "show_quantity",
        "show_store",
        "show_vintage",
        "show_prices",
        "item_count",
        "sort_order",
        "created_at",
    )
    list_filter = (
        "user",
        "list_type",
        "show_quantity",
        "show_store",
        "show_vintage",
        "show_prices",
    )
    search_fields = ("name", "user__username")
    fields = (
        "user",
        "name",
        "description",
        "list_type",
        "show_quantity",
        "show_store",
        "show_vintage",
        "show_prices",
        "selected_store_id",
        "event_date",
        "sort_order",
        "share_token",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("user", "share_token", "created_at", "updated_at")
    inlines = [UserListItemInline]

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()


admin.site.register(UserList, UserListAdmin)


@admin.register(UserWithLists)
class UserWithListsAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "list_count")
    search_fields = ("username", "email")
    fields = ("username", "email")
    readonly_fields = ("username", "email")
    inlines = [UserListInline]
    actions = ["delete_all_lists"]

    @admin.action(description="Delete all lists for selected users")
    def delete_all_lists(self, request, queryset):
        count, _ = UserList.objects.filter(user__in=queryset).delete()
        self.message_user(request, f"Deleted {count} lists.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(list_count=Count("lists")).filter(list_count__gt=0)

    @admin.display(ordering="list_count")
    def list_count(self, obj):
        return obj.list_count


class UntappdCheckinInline(admin.TabularInline):
    model = UntappdCheckin
    extra = 0
    max_num = 50
    fields = ("untpd_checkin_id", "untpd_beer_id", "rating", "checkin_at", "synced")
    readonly_fields = (
        "untpd_checkin_id",
        "untpd_beer_id",
        "rating",
        "checkin_at",
        "synced",
    )
    ordering = ("-checkin_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        limited_ids = list(qs.order_by("-checkin_at").values_list("pk", flat=True)[:50])
        return qs.filter(pk__in=limited_ids).order_by("-checkin_at")


@admin.register(UserWithCheckins)
class UserWithCheckinsAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "checkin_count", "unsynced_count")
    search_fields = ("username", "email")
    fields = ("username", "email")
    readonly_fields = ("username", "email")
    inlines = [UntappdCheckinInline]
    actions = ["delete_all_checkins"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.action(description="Delete all checkins for selected users")
    def delete_all_checkins(self, request, queryset):
        count, _ = UntappdCheckin.objects.filter(user__in=queryset).delete()
        self.message_user(request, f"Deleted {count} checkins.")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            checkin_count=Count("untappd_checkins"),
            unsynced_count=Count(
                "untappd_checkins", filter=models.Q(untappd_checkins__synced=False)
            ),
        ).filter(checkin_count__gt=0)

    @admin.display(ordering="checkin_count")
    def checkin_count(self, obj):
        return obj.checkin_count

    @admin.display(ordering="unsynced_count")
    def unsynced_count(self, obj):
        return obj.unsynced_count


@admin.register(UntappdRssFeed)
class UntappdRssFeedAdmin(admin.ModelAdmin):
    list_display = ("user", "feed_url", "last_synced", "active")
    list_filter = ("active",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("last_synced", "created_at")


@admin.register(FollowedList)
class FollowedListAdmin(admin.ModelAdmin):
    list_display = ("user", "share_token", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "share_token")
    raw_id_fields = ("user",)


admin.site.register(Badge)
admin.site.register(ExternalAPI)
admin.site.register(Option)
admin.site.register(UntappdList)
admin.site.register(VmpNotReleased)
admin.site.register(WrongMatch)
