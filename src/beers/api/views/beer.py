from __future__ import annotations

from django.core.cache import cache
from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from beers.api.filters import BeerFilter, NullsAlwaysLastOrderingFilter
from beers.api.pagination import LargeResultPagination
from beers.api.serializers import BeerSerializer
from beers.api.utils import bulk_import_tasted, parse_untappd_file
from beers.api.views.base import BrowsableMixin
from beers.models import Beer, Stock, Tasted
from clients.vmp import VmpApiError, VmpBlockedError, VmpClient

_BARCODE_HIT_TTL = 60 * 60 * 24 * 30
_BARCODE_MISS_TTL = 60 * 60


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
        "brewery__name",
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
    ordering = ["pk"]

    def get_queryset(self) -> QuerySet[Beer]:
        queryset = (
            Beer.objects.with_user_tasted(self.request.user)
            .select_related("country", "brewery")
            .prefetch_related(
                "badge_set",
                Prefetch("stock_set", queryset=Stock.objects.select_related("store")),
            )
        )

        beers = getattr(self.request, "query_params", {}).get("beers")
        if beers is not None:
            beer_ids = [int(v) for v in beers.split(",")]
            queryset = queryset.filter(vmp_id__in=beer_ids)

        return queryset

    @action(detail=False, methods=["get"], url_path="barcode")
    def barcode(self, request):
        code = (request.query_params.get("code") or "").strip()
        if not code.isdigit():
            return Response({"error": "A numeric barcode is required"}, status=400)

        if cache.get(f"vmp_barcode_miss:{code}"):
            return Response({"error": "No beer found for this barcode"}, status=404)

        vmp_code = cache.get(f"vmp_barcode:{code}")
        if vmp_code is None:
            try:
                vmp_code = VmpClient.from_external_api().barcode_search(code)
            except VmpBlockedError:
                return Response(
                    {"error": "Barcode lookup temporarily unavailable"}, status=503
                )
            except VmpApiError:
                return Response({"error": "Barcode lookup failed"}, status=502)

            if vmp_code is None:
                cache.set(f"vmp_barcode_miss:{code}", True, _BARCODE_MISS_TTL)
                return Response({"error": "No beer found for this barcode"}, status=404)

            cache.set(f"vmp_barcode:{code}", vmp_code, _BARCODE_HIT_TTL)

        beer = self.get_queryset().filter(vmp_id=int(vmp_code)).first()
        if beer is None:
            return Response({"error": "No beer found for this barcode"}, status=404)

        return Response(self.get_serializer(beer).data)

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
            _tasted, created = Tasted.objects.get_or_create(
                user=request.user, beer=beer
            )
            if created:
                return Response({"status": "marked as tasted"}, status=201)
            return Response({"status": "already marked as tasted"}, status=200)

        deleted_count, _ = Tasted.objects.filter(user=request.user, beer=beer).delete()
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
        except Exception:
            return Response({"error": "Failed to parse file"}, status=400)

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
