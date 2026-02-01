from __future__ import annotations

from beers.api.filters import (
    BeerFilter,
    NullsAlwaysLastOrderingFilter,
    StockChangeFilter,
)
from beers.api.pagination import LargeResultPagination, Pagination
from beers.api.serializers import (
    BeerSerializer,
    CountrySerializer,
    ListReorderSerializer,
    ProductReorderSerializer,
    ReleaseSerializer,
    SharedUserListSerializer,
    StockChangeSerializer,
    StockSerializer,
    StoreSerializer,
    UserListCreateSerializer,
    UserListSerializer,
    WrongMatchSerializer,
)
from beers.api.utils import bulk_import_tasted, parse_untappd_file
from beers.models import (
    Beer,
    Country,
    Release,
    Stock,
    Store,
    Tasted,
    UserList,
    UserListItem,
    WrongMatch,
)
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Count, Exists, F, Max, OuterRef, Q, Value
from django.db.models.functions import Greatest
from django.db.models.manager import BaseManager
from django_filters.rest_framework import DjangoFilterBackend
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
        return UserList.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return UserListCreateSerializer
        return UserListSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["patch"], url_path="reorder")
    def reorder_lists(self, request):
        serializer = ListReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for item in serializer.validated_data["order"]:
            UserList.objects.filter(id=item["id"], user=request.user).update(
                sort_order=item["sort_order"]
            )

        return Response({"status": "ok"})

    @action(
        detail=True,
        methods=["post", "delete"],
        url_path=r"products/(?P<product_id>\d+)",
    )
    def product(self, request, pk=None, product_id=None):
        user_list = self.get_object()

        if request.method == "POST":
            if not Beer.objects.filter(vmp_id=product_id).exists():
                return Response({"error": "Product not found"}, status=404)

            max_position = (
                user_list.items.aggregate(max_pos=Max("position"))["max_pos"] or 0
            )
            item, created = UserListItem.objects.get_or_create(
                list=user_list,
                product_id=product_id,
                defaults={"position": max_position + 1},
            )
            if not created:
                return Response({"error": "Product already in list"}, status=400)
            return Response({"status": "added", "product_id": product_id}, status=201)

        if request.method == "DELETE":
            deleted, _ = UserListItem.objects.filter(
                list=user_list, product_id=product_id
            ).delete()
            if not deleted:
                return Response({"error": "Product not in list"}, status=404)
            return Response(status=204)

    @action(detail=True, methods=["patch"], url_path="products/reorder")
    def reorder_products(self, request, pk=None):
        user_list = self.get_object()
        serializer = ProductReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for item in serializer.validated_data["order"]:
            UserListItem.objects.filter(
                list=user_list, product_id=item["product_id"]
            ).update(position=item["position"])

        return Response({"status": "ok"})

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
            return Response({"error": "List not found"}, status=404)

        serializer = SharedUserListSerializer(user_list)
        return Response(serializer.data)
