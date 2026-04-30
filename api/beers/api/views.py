from __future__ import annotations

import json as _json

from beers.api.filters import (
    BeerFilter,
    NullsAlwaysLastOrderingFilter,
    StockChangeFilter,
)
from beers.api.pagination import LargeResultPagination, Pagination
from beers.api.serializers import (
    BeerSerializer,
    CountrySerializer,
    ItemReorderSerializer,
    ListReorderSerializer,
    ReleaseSerializer,
    SharedUserListSerializer,
    StockChangeSerializer,
    StockSerializer,
    StoreSerializer,
    UntappdListSearchResultSerializer,
    UntappdListSubscribeSerializer,
    UntappdRssFeedSerializer,
    UserListCreateSerializer,
    UserListItemCreateSerializer,
    UserListItemSerializer,
    UserListItemUpdateSerializer,
    UserListSerializer,
    UserListUpdateSerializer,
    WrongMatchSerializer,
)
from beers.models import (
    Beer,
    Country,
    Release,
    Stock,
    Store,
    Tasted,
    UntappdList,
    UntappdRssFeed,
    UserList,
    UserListItem,
    WrongMatch,
)
from beers.untappd_lists import fetch_user_lists
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import models
from django.db.models import Count, Exists, F, OuterRef, Q, QuerySet, Value
from django.db.models.functions import Greatest
from django_filters.rest_framework import DjangoFilterBackend
from django_q.tasks import async_task
from rest_framework import filters, permissions
from rest_framework.decorators import action
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet


class BrowsableMixin:
    def get_renderers(self) -> list:
        renderers = list(getattr(self, "renderer_classes", []))
        request = getattr(self, "request", None)
        if request and getattr(request, "user", None):
            renderers.append(BrowsableAPIRenderer)
        return [renderer() for renderer in renderers]


class BeerViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = BeerSerializer
    pagination_class = LargeResultPagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]
    filter_backends = (
        filters.SearchFilter,
        NullsAlwaysLastOrderingFilter,
        DjangoFilterBackend,
    )
    search_fields = [
        "vmp_name",
        "brewery",
        "sub_category",
        "style",
        "vmp_id",
        "untpd_id",
    ]
    ordering_fields = [
        "vmp_name",
        "brewery",
        "rating",
        "price",
        "created_at",
        "abv",
        "price_per_volume",
        "price_per_alcohol_unit",
        "value_score",
        "checkin__rating",
        "tasted__rating",
    ]
    filterset_class = BeerFilter

    def get_queryset(self) -> QuerySet[Beer]:
        queryset = Beer.objects.all()
        queryset = queryset.prefetch_related("badge_set", "stock_set")

        if self.request.user and self.request.user.is_authenticated:
            queryset = queryset.annotate(
                user_tasted=Exists(
                    Tasted.objects.filter(user=self.request.user, beer=OuterRef("pk"))
                )
            )
        else:
            queryset = queryset.annotate(user_tasted=Value(False))

        beers = getattr(self.request, "query_params", {}).get("beers")
        if beers is not None:
            beer_ids = [int(v) for v in beers.split(",")]
            queryset = queryset.filter(vmp_id__in=beer_ids)

        return queryset

    @action(detail=False, methods=["get"], url_path="styles")
    def styles(self, request):
        styles = (
            Beer.objects.filter(active=True, style__isnull=False)
            .exclude(style="")
            .values_list("style", flat=True)
            .distinct()
            .order_by("style")
        )
        return Response(list(styles))


class StockChangeViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = StockChangeSerializer
    pagination_class = Pagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = StockChangeFilter

    def get_queryset(self) -> QuerySet[Stock]:
        return (
            Stock.objects.all()
            .exclude(Q(stocked_at=None) & Q(unstocked_at=None))
            .annotate(stock_unstock_at=Greatest("stocked_at", "unstocked_at"))
            .select_related("store", "beer")
            .order_by(
                F("stock_unstock_at__date").desc(),
                F("stocked_at").desc(nulls_last=True),
            )
        )


class StoreViewSet(BrowsableMixin, ModelViewSet):
    queryset = Store.objects.all().order_by("name")
    serializer_class = StoreSerializer
    pagination_class = LargeResultPagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]

    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ["name", "address", "store_id"]
    ordering_fields = ["name", "store_id"]
    ordering = ["name"]


class StockViewSet(BrowsableMixin, ModelViewSet):
    queryset = (
        Stock.objects.all().order_by("store__store_id").select_related("store", "beer")
    )
    serializer_class = StockSerializer
    pagination_class = Pagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["store", "beer"]


class WrongMatchViewSet(BrowsableMixin, ModelViewSet):
    queryset = WrongMatch.objects.all().select_related("beer")
    serializer_class = WrongMatchSerializer
    pagination_class = Pagination
    permission_classes = [permissions.AllowAny]


class ReleaseViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = ReleaseSerializer
    pagination_class = Pagination
    permission_classes = [permissions.AllowAny]

    def get_queryset(self) -> QuerySet[Release]:
        return (
            Release.objects.filter(active=True)
            .order_by("-release_date")
            .prefetch_related("beer")
            .annotate(
                product_count=Count("beer", distinct=True),
                beer_count=Count(
                    "beer", filter=Q(beer__main_category__iexact="Øl"), distinct=True
                ),
                cider_count=Count(
                    "beer", filter=Q(beer__main_category__iexact="Sider"), distinct=True
                ),
                mead_count=Count(
                    "beer", filter=Q(beer__main_category__iexact="Mjød"), distinct=True
                ),
                product_selections=ArrayAgg("beer__product_selection", distinct=True),
            )
        )

    @action(detail=True, methods=["get"], url_path="countries")
    def countries(self, request, pk=None):
        release = self.get_object()
        countries = (
            Country.objects.filter(beers__in=release.beer.all())
            .distinct()
            .order_by("name")
        )
        serializer = CountrySerializer(countries, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="styles")
    def styles(self, request, pk=None):
        release = self.get_object()
        styles = (
            release.beer.filter(style__isnull=False)
            .exclude(style="")
            .values_list("style", flat=True)
            .distinct()
            .order_by("style")
        )
        return Response(list(styles))


class CountryViewSet(BrowsableMixin, ModelViewSet):
    queryset = Country.objects.all().order_by("name")
    serializer_class = CountrySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ["name", "iso_code"]
    ordering_fields = ["name", "iso_code"]
    ordering = ["name"]

    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        countries = (
            Country.objects.filter(beers__active=True).distinct().order_by("name")
        )
        serializer = self.get_serializer(countries, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="unmapped")
    def unmapped(self, request):
        countries = Country.objects.filter(iso_code__isnull=True).order_by("name")
        serializer = self.get_serializer(countries, many=True)
        return Response(serializer.data)


class UserListViewSet(BrowsableMixin, ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        if self.action == "create":
            return UserListCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserListUpdateSerializer
        return UserListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "retrieve":
            context["include_items"] = True
        return context

    def get_queryset(self) -> QuerySet[UserList]:
        return (
            UserList.objects.filter(user=self.request.user)
            .select_related("untappd_list")
            .prefetch_related("items")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance: UserList) -> None:
        untappd_list = instance.untappd_list
        instance.delete()
        if (
            untappd_list
            and not UserList.objects.filter(untappd_list=untappd_list).exists()
        ):
            untappd_list.delete()

    @action(detail=True, methods=["get"], url_path="share")
    def share(self, request, pk=None):
        user_list = self.get_object()
        serializer = SharedUserListSerializer(user_list)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="shared/(?P<token>[^/.]+)",
        permission_classes=[permissions.AllowAny],
    )
    def shared(self, request, token: str | None = None):
        user_list = UserList.objects.filter(share_token=token).first()
        if not user_list:
            return Response(status=404)
        serializer = SharedUserListSerializer(user_list)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="items")
    def add_item(self, request, pk=None):
        user_list = self.get_object()
        if user_list.list_type == UserList.ListType.UNTAPPD:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        serializer = UserListItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        max_order = user_list.items.aggregate(m=models.Max("sort_order"))["m"] or 0
        serializer.save(list=user_list, sort_order=max_order + 1)
        return Response(UserListItemSerializer(serializer.instance).data, status=201)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"items/(?P<item_pk>\d+)",
    )
    def item_detail(self, request, pk=None, item_pk: str | None = None):
        user_list = self.get_object()
        if user_list.list_type == UserList.ListType.UNTAPPD:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        item = user_list.items.filter(pk=item_pk).first()
        if not item:
            return Response(status=404)
        if request.method == "DELETE":
            item.delete()
            return Response(status=204)
        serializer = UserListItemUpdateSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserListItemSerializer(serializer.instance).data)

    @action(
        detail=True,
        methods=["delete"],
        url_path="products/(?P<product_id>[^/.]+)",
    )
    def product_detail(self, request, pk=None, product_id=None):
        user_list = self.get_object()
        if user_list.list_type == UserList.ListType.UNTAPPD:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        item = user_list.items.filter(product_id=product_id).first()
        if not item:
            return Response(status=404)
        item.delete()
        return Response(status=204)

    @action(detail=False, methods=["post", "patch"], url_path="reorder")
    def reorder_lists(self, request):
        serializer = ListReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        list_ids: list[int] = serializer.validated_data["list_ids"]
        for i, list_id in enumerate(list_ids):
            UserList.objects.filter(pk=list_id, user=request.user).update(sort_order=i)
        return Response(status=204)

    @action(detail=True, methods=["post", "patch"], url_path="items/reorder")
    def reorder_items(self, request, pk=None):
        user_list = self.get_object()
        if user_list.list_type == UserList.ListType.UNTAPPD:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        serializer = ItemReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item_ids: list[int] = serializer.validated_data["item_ids"]
        for i, item_id in enumerate(item_ids):
            UserListItem.objects.filter(pk=item_id, list=user_list).update(sort_order=i)
        return Response(status=204)


class UntappdListViewSet(BrowsableMixin, ModelViewSet):
    queryset = UntappdList.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post"]
    lookup_field = "untappd_list_id"

    def list(self, request):
        return Response(status=405)

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        username = request.query_params.get("username", "").strip()
        if not username:
            return Response({"detail": "username parameter is required"}, status=400)

        try:
            lists = fetch_user_lists(username)
        except ValueError as e:
            return Response({"detail": str(e)}, status=404)
        except Exception:
            return Response(
                {"detail": "Failed to fetch lists from Untappd"}, status=502
            )

        serializer = UntappdListSearchResultSerializer(lists, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe(self, request):
        serializer = UntappdListSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        untappd_list, _created = UntappdList.objects.get_or_create(
            untappd_list_id=data["untappd_list_id"],
            untappd_username=data["untappd_username"],
            defaults={
                "name": data["name"],
                "is_wishlist": data["untappd_list_id"] == 0,
            },
        )

        existing = UserList.objects.filter(
            user=request.user, untappd_list=untappd_list
        ).first()
        if existing:
            return Response(UserListSerializer(existing).data, status=200)

        user_list = UserList.objects.create(
            user=request.user,
            name=data["name"],
            list_type=UserList.ListType.UNTAPPD,
            untappd_list=untappd_list,
        )

        task_id = async_task(
            "beers.tasks.sync_untappd_list_task",
            untappd_list.pk,
        )
        untappd_list.sync_task_id = task_id
        untappd_list.save(update_fields=["sync_task_id"])

        return Response(UserListSerializer(user_list).data, status=201)

    @action(detail=True, methods=["post"], url_path="sync")
    def sync(self, request, untappd_list_id=None):
        user_list = (
            UserList.objects.filter(
                user=request.user, untappd_list__untappd_list_id=untappd_list_id
            )
            .select_related("untappd_list")
            .first()
        )
        if not user_list or not user_list.untappd_list:
            return Response(status=404)

        task_id = async_task(
            "beers.tasks.sync_untappd_list_task",
            user_list.untappd_list.pk,
        )
        user_list.untappd_list.sync_task_id = task_id
        user_list.untappd_list.save(update_fields=["sync_task_id"])

        return Response(UserListSerializer(user_list).data, status=202)


class UntappdRssFeedViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = UntappdRssFeedSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "put", "patch", "delete"]

    def get_queryset(self) -> QuerySet[UntappdRssFeed]:
        return UntappdRssFeed.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        feed = self.get_queryset().first()
        if not feed:
            return Response(status=404)
        return Response(self.get_serializer(feed).data)

    @action(detail=False, methods=["get", "put", "patch", "delete"])
    def me(self, request):
        feed = UntappdRssFeed.objects.filter(user=request.user).first()
        if request.method == "GET":
            if not feed:
                return Response(status=404)
            return Response(self.get_serializer(feed).data)
        if request.method == "DELETE":
            if feed:
                feed.delete()
            return Response(status=204)
        if not feed:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user)
            return Response(serializer.data, status=201)
        serializer = self.get_serializer(
            feed, data=request.data, partial=request.method == "PATCH"
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def sync(self, request):
        from beers.tasks import sync_rss_feeds

        feed = UntappdRssFeed.objects.filter(user=request.user, active=True).first()
        if not feed:
            return Response({"error": "No active RSS feed configured"}, status=404)
        try:
            output = sync_rss_feeds(user=request.user.username)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
        for line in reversed(output.strip().splitlines()):
            try:
                summary = _json.loads(line)
            except (ValueError, TypeError):
                continue
            summary.pop("users_affected", None)
            return Response(summary)
        return Response({"imported": 0, "synced": 0})
