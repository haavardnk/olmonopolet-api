from __future__ import annotations

from beers.models import Beer, Stock
from django.db.models import F, Q, QuerySet
from django.http import HttpRequest
from django_filters import rest_framework as flt
from rest_framework import filters
from rest_framework.views import APIView


class NullsAlwaysLastOrderingFilter(filters.OrderingFilter):
    def filter_queryset(
        self, request: HttpRequest, queryset: QuerySet[Beer], view: APIView
    ) -> QuerySet[Beer]:
        ordering = self.get_ordering(request, queryset, view)

        if ordering:
            f_ordering: list = []
            for field_name in ordering:
                if not field_name:
                    continue

                if field_name.startswith("-"):
                    f_ordering.append(F(field_name[1:]).desc(nulls_last=True))
                else:
                    f_ordering.append(F(field_name).asc(nulls_last=True))

            return queryset.order_by(*f_ordering)

        return queryset


class BeerFilter(flt.FilterSet):
    style = flt.CharFilter(method="custom_style_filter")
    product_selection = flt.CharFilter(method="custom_product_selection_filter")
    store = flt.CharFilter(method="custom_store_filter")
    country = flt.CharFilter(method="custom_country_filter")
    price_high = flt.NumberFilter(field_name="price", lookup_expr="lte")
    price_low = flt.NumberFilter(field_name="price", lookup_expr="gte")
    ppv_high = flt.NumberFilter(field_name="price_per_volume", lookup_expr="lte")
    ppv_low = flt.NumberFilter(field_name="price_per_volume", lookup_expr="gte")
    abv_high = flt.NumberFilter(field_name="abv", lookup_expr="lte")
    abv_low = flt.NumberFilter(field_name="abv", lookup_expr="gte")
    release = flt.CharFilter(method="custom_release_filter")
    exclude_allergen = flt.CharFilter(method="custom_allergen_filter")

    def _build_multi_value_query(self, values: str, field_lookup: str) -> Q:
        query = Q()
        for value in values.split(","):
            value = value.strip()
            if value:
                query |= Q(**{field_lookup: value})
        return query

    def custom_style_filter(
        self, queryset: QuerySet[Beer], name: str, value: str
    ) -> QuerySet[Beer]:
        query = self._build_multi_value_query(value, "style__icontains")
        return queryset.filter(query).distinct()

    def custom_product_selection_filter(
        self, queryset: QuerySet[Beer], name: str, value: str
    ) -> QuerySet[Beer]:
        query = self._build_multi_value_query(value, "product_selection__iexact")
        return queryset.filter(query).distinct()

    def custom_store_filter(
        self, queryset: QuerySet[Beer], name: str, value: str
    ) -> QuerySet[Beer]:
        query = Q()
        for store_id in value.split(","):
            store_id = store_id.strip()
            if store_id.isdigit():
                query |= Q(stock__store__exact=int(store_id)) & ~Q(stock__quantity=0)
        return queryset.filter(query).distinct()

    def custom_country_filter(
        self, queryset: QuerySet[Beer], name: str, value: str
    ) -> QuerySet[Beer]:
        query = self._build_multi_value_query(value, "country__name__iexact")
        return queryset.filter(query).distinct()

    def custom_release_filter(
        self, queryset: QuerySet[Beer], name: str, value: str
    ) -> QuerySet[Beer]:
        query = self._build_multi_value_query(value, "release__name__iexact")
        return queryset.filter(query).distinct()

    def custom_allergen_filter(
        self, queryset: QuerySet[Beer], name: str, value: str
    ) -> QuerySet[Beer]:
        query = self._build_multi_value_query(value, "allergens__icontains")
        return queryset.exclude(query).distinct()

    class Meta:
        model = Beer
        fields = [
            "style",
            "brewery",
            "product_selection",
            "active",
            "store",
            "country",
            "price_high",
            "price_low",
            "ppv_high",
            "ppv_low",
            "abv_high",
            "abv_low",
            "release",
            "exclude_allergen",
            "post_delivery",
            "store_delivery",
        ]


class StockChangeFilter(flt.FilterSet):
    store = flt.CharFilter(method="custom_store_filter")

    def custom_store_filter(
        self, queryset: QuerySet[Stock], name: str, value: str
    ) -> QuerySet[Stock]:
        if value.isdigit():
            return queryset.filter(store__exact=int(value)).distinct()
        return queryset.none()

    class Meta:
        model = Stock
        fields = [
            "store",
        ]
