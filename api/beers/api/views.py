from beers.api.filters import (
    BeerFilter,
    NullsAlwaysLastOrderingFilter,
    StockChangeFilter,
)
from beers.api.pagination import LargeResultPagination, Pagination
from beers.api.serializers import (
    BeerSerializer,
    ReleaseSerializer,
    StockChangeSerializer,
    StockSerializer,
    StoreSerializer,
    WrongMatchSerializer,
)
from beers.models import Beer, Release, Stock, Store, WrongMatch
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Count, F, Q
from django.db.models.functions import Greatest
from django.db.models.manager import BaseManager
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.viewsets import ModelViewSet


class BrowsableMixin(object):
    def get_renderers(self):
        rends = self.renderer_classes  # type: ignore
        if self.request.user:  # type: ignore
            rends.append(BrowsableAPIRenderer)
        return [renderer() for renderer in rends]


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
        "checkin__rating",
        "tasted__rating",
    ]
    filterset_class = BeerFilter

    def get_queryset(self) -> BaseManager[Beer]:
        queryset = Beer.objects.all()
        # Prefetch related objects for serializer speed
        queryset = queryset.prefetch_related(
            "badge_set",
            "stock_set",
        )
        beers = self.request.query_params.get("beers", None)  # type: ignore[attr-defined]

        if beers is not None:
            beers = list(int(v) for v in beers.split(","))
            queryset = queryset.filter(vmp_id__in=beers)

        return queryset


class StockChangeViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = StockChangeSerializer
    pagination_class = Pagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = StockChangeFilter

    def get_queryset(self):
        queryset = (
            Stock.objects.all()
            .exclude(Q(stocked_at=None) & Q(unstocked_at=None))
            .annotate(stock_unstock_at=Greatest("stocked_at", "unstocked_at"))
            .select_related("store", "beer")
            .order_by(
                F("stock_unstock_at__date").desc(),
                F("stocked_at").desc(nulls_last=True),
            )
        )
        return queryset


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
    queryset = (
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
    serializer_class = ReleaseSerializer
    pagination_class = Pagination
    permission_classes = [permissions.AllowAny]
