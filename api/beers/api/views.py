from __future__ import annotations

import json

from beers.api.filters import (BeerFilter, NullsAlwaysLastOrderingFilter,
                               StockChangeFilter)
from beers.api.pagination import LargeResultPagination, Pagination
from beers.api.serializers import (BeerSerializer, CountrySerializer,
                                   ItemReorderSerializer,
                                   ListReorderSerializer, ReleaseSerializer,
                                   SharedUserListSerializer,
                                   StockChangeSerializer, StockSerializer,
                                   StoreSerializer, UntappdRssFeedSerializer,
                                   UserListCreateSerializer,
                                   UserListItemCreateSerializer,
                                   UserListItemSerializer,
                                   UserListItemUpdateSerializer,
                                   UserListSerializer,
                                   UserListUpdateSerializer,
                                   WrongMatchSerializer)
from beers.api.utils import bulk_import_tasted, parse_untappd_file
from beers.models import (Beer, Country, Release, Stock, Store, Tasted,
                          UntappdRssFeed, UserList, UserListItem, WrongMatch)
from beers.tasks import sync_rss_feeds
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import (Count, Exists, F, Max, OuterRef, Prefetch, Q,
                              Value)
from django.db.models.functions import Greatest
from django.db.models.manager import BaseManager
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status
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
        "abv",
        "brewery",
        "checkin__rating",
        "created_at",
        "price",
        "price_per_alcohol_unit",
        "price_per_volume",
        "rating",
        "tasted__rating",
        "vmp_name",
    ]
    filterset_class = BeerFilter

    def get_queryset(self) -> BaseManager[Beer]:
        queryset = Beer.objects.all()
        queryset = queryset.prefetch_related("badge_set", "stock_set")

        if self.request.user and self.request.user.is_authenticated:
            user_tasted_subquery = Tasted.objects.filter(
                user=self.request.user, beer=OuterRef("pk")
            )
            queryset = queryset.annotate(user_tasted=Exists(user_tasted_subquery))
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

    @action(
        detail=True,
        methods=["post", "delete"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def mark_tasted(self, request, pk=None):
        beer = self.get_object()

        if request.method == "POST":
            tasted, created = Tasted.objects.get_or_create(user=request.user, beer=beer)
            if created:
                return Response({"status": "marked as tasted"}, status=201)
            return Response({"status": "already marked as tasted"}, status=200)

        elif request.method == "DELETE":
            deleted_count, _ = Tasted.objects.filter(
                user=request.user, beer=beer
            ).delete()
            if deleted_count > 0:
                return Response({"status": "removed from tasted"}, status=204)
            return Response({"status": "not found"}, status=404)

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def bulk_mark_tasted(self, request) -> Response:
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "No file provided"}, status=400)

        try:
            checkins = parse_untappd_file(uploaded_file)
        except Exception as e:
            return Response(
                {"error": "Failed to parse file", "details": str(e)}, status=400
            )

        if checkins is None:
            return Response(
                {"error": "Unsupported file format. Use .csv or .json"}, status=400
            )

        if not checkins:
            return Response({"error": "No valid beer IDs found in file"}, status=400)

        result = bulk_import_tasted(request.user, checkins)

        return Response(
            {
                **result,
                "message": f"Successfully imported {result['imported_count']} beers from {result['total_check_ins']} check-ins",
            },
            status=200,
        )


class StockChangeViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = StockChangeSerializer
    pagination_class = Pagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = StockChangeFilter

    def get_queryset(self) -> BaseManager[Stock]:
        beer_qs = Beer.objects.all()
        if self.request.user and self.request.user.is_authenticated:
            user_tasted_subquery = Tasted.objects.filter(
                user=self.request.user, beer=OuterRef("pk")
            )
            beer_qs = beer_qs.annotate(user_tasted=Exists(user_tasted_subquery))
        else:
            beer_qs = beer_qs.annotate(user_tasted=Value(False))

        return (
            Stock.objects.all()
            .exclude(Q(stocked_at=None) & Q(unstocked_at=None))
            .annotate(stock_unstock_at=Greatest("stocked_at", "unstocked_at"))
            .select_related("store")
            .prefetch_related(Prefetch("beer", queryset=beer_qs))
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

    def get_queryset(self) -> BaseManager[Release]:
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
    serializer_class = UserListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserList.objects.filter(user=self.request.user).prefetch_related("items")

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

    def perform_create(self, serializer):
        max_sort = (
            UserList.objects.filter(user=self.request.user).aggregate(
                max_sort=Max("sort_order")
            )["max_sort"]
            or 0
        )
        serializer.save(user=self.request.user, sort_order=max_sort + 1)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_serializer = UserListSerializer(
            serializer.instance, context={"include_items": True}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        response_serializer = UserListSerializer(
            instance, context={"include_items": True}
        )
        return Response(response_serializer.data)

    @action(detail=False, methods=["patch"], url_path="reorder")
    def reorder_lists(self, request):
        serializer = ListReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        list_ids = serializer.validated_data["list_ids"]
        for index, list_id in enumerate(list_ids):
            UserList.objects.filter(id=list_id, user=request.user).update(
                sort_order=index
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="items")
    def add_item(self, request, pk=None):
        user_list = self.get_object()
        serializer = UserListItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_id = serializer.validated_data["product_id"]

        if not Beer.objects.filter(vmp_id=product_id).exists():
            return Response(
                {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if UserListItem.objects.filter(list=user_list, product_id=product_id).exists():
            return Response(
                {"error": "Product already in list"}, status=status.HTTP_409_CONFLICT
            )

        max_sort = (
            user_list.items.aggregate(max_sort=Max("sort_order"))["max_sort"] or 0
        )

        item = UserListItem.objects.create(
            list=user_list,
            product_id=product_id,
            quantity=serializer.validated_data.get("quantity", 1),
            year=serializer.validated_data.get("year"),
            notes=serializer.validated_data.get("notes"),
            sort_order=max_sort + 1,
        )

        response_serializer = UserListItemSerializer(
            item, context={"selected_store_id": user_list.selected_store_id}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"items/(?P<item_id>\d+)",
    )
    def item_detail(self, request, pk=None, item_id=None):
        user_list = self.get_object()

        try:
            item = user_list.items.get(id=item_id)
        except UserListItem.DoesNotExist:
            return Response(
                {"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if request.method == "DELETE":
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = UserListItemUpdateSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = UserListItemSerializer(
            item, context={"selected_store_id": user_list.selected_store_id}
        )
        return Response(response_serializer.data)

    @action(detail=True, methods=["patch"], url_path="items/reorder")
    def reorder_items(self, request, pk=None):
        user_list = self.get_object()
        serializer = ItemReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item_ids = serializer.validated_data["item_ids"]
        for index, item_id in enumerate(item_ids):
            UserListItem.objects.filter(list=user_list, id=item_id).update(
                sort_order=index
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"shared/(?P<share_token>[^/.]+)",
        permission_classes=[permissions.AllowAny],
    )
    def shared(self, request, share_token=None):
        try:
            user_list = UserList.objects.get(share_token=share_token)
        except UserList.DoesNotExist:
            return Response(
                {"error": "List not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = SharedUserListSerializer(user_list)
        return Response(serializer.data)


class UntappdRssFeedViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = UntappdRssFeedSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "delete"]

    def get_queryset(self):
        return UntappdRssFeed.objects.filter(user=self.request.user)

    def get_object(self):
        try:
            return UntappdRssFeed.objects.get(user=self.request.user)
        except UntappdRssFeed.DoesNotExist:
            from django.http import Http404

            raise Http404

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        if UntappdRssFeed.objects.filter(user=request.user).exists():
            return Response(
                {"error": "RSS feed already configured. Use PUT/PATCH to update."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        try:
            instance = UntappdRssFeed.objects.get(user=request.user)
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except UntappdRssFeed.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=["post"], url_path="sync")
    def sync(self, request):
        if not UntappdRssFeed.objects.filter(user=request.user, active=True).exists():
            return Response(
                {"error": "No active RSS feed configured"},
                status=status.HTTP_404_NOT_FOUND,
            )

        output = sync_rss_feeds(user=request.user.username)
        for line in reversed(output.strip().splitlines()):
            try:
                summary = json.loads(line)
                summary.pop("users_affected", None)
                return Response(summary)
            except json.JSONDecodeError:
                continue
        return Response({"imported": 0, "synced": 0})
