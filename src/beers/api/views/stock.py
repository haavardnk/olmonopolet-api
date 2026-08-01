from __future__ import annotations

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from rest_framework.viewsets import ModelViewSet

from beers.api.views.base import BrowsableMixin
from beers.api.filters import StockChangeFilter
from beers.api.pagination import LargeResultPagination, Pagination
from beers.api.serializers import (
    StockChangeSerializer,
    StockSerializer,
    StoreSerializer,
)
from beers.models import Beer, Stock, Store


class StockChangeViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = StockChangeSerializer
    pagination_class = Pagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = StockChangeFilter

    def get_queryset(self) -> QuerySet[Stock]:
        beer_qs = Beer.objects.with_user_tasted(self.request.user)

        return (
            Stock.objects.stock_changes()
            .select_related("store")
            .prefetch_related(Prefetch("beer", queryset=beer_qs))
        )


class StoreViewSet(BrowsableMixin, ModelViewSet):
    queryset = Store.objects.all().order_by("name", "store_id")
    serializer_class = StoreSerializer
    pagination_class = LargeResultPagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]

    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ["name", "address", "store_id"]
    ordering_fields = ["name", "store_id"]
    ordering = ["name", "store_id"]


class StockViewSet(BrowsableMixin, ModelViewSet):
    queryset = (
        Stock.objects.all()
        .order_by("store__store_id", "pk")
        .select_related("store", "beer")
    )
    serializer_class = StockSerializer
    pagination_class = Pagination
    permission_classes = [permissions.DjangoModelPermissionsOrAnonReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["store", "beer"]
