from __future__ import annotations

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Count, Q, QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from beers.api.views.base import PUBLIC_CACHE_SECONDS, BrowsableMixin
from beers.api.pagination import Pagination
from beers.api.serializers import CountrySerializer, ReleaseSerializer
from beers.models import Country, Release


@method_decorator(cache_page(PUBLIC_CACHE_SECONDS), name="dispatch")
class ReleaseViewSet(BrowsableMixin, ReadOnlyModelViewSet):
    serializer_class = ReleaseSerializer
    pagination_class = Pagination
    permission_classes = [permissions.AllowAny]

    def get_queryset(self) -> QuerySet[Release]:
        qs = Release.objects.filter(active=True).order_by("-release_date", "pk")
        if self.action in ("list", "retrieve"):
            qs = qs.annotate(
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
        return qs

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


@method_decorator(cache_page(PUBLIC_CACHE_SECONDS), name="dispatch")
class CountryViewSet(BrowsableMixin, ReadOnlyModelViewSet):
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
