from django.db.models import F
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from beers.api.views.base import PUBLIC_CACHE_SECONDS
from extension.models import ExtensionConfig, ExtensionReport

PAGES = ["search", "details", "cart", "wishlist"]


class ReportSerializer(serializers.Serializer):
    version = serializers.RegexField(r"^\d+\.\d+\.\d+$", max_length=20)
    page = serializers.ChoiceField(choices=PAGES)
    anchors = serializers.ListField(
        child=serializers.RegexField(r"^[a-zA-Z][a-zA-Z0-9_]*$", max_length=50),
        min_length=1,
        max_length=20,
    )


class ExtensionConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        config = ExtensionConfig.objects.order_by("-updated_at").first()
        if config is None:
            return Response(status=404)
        response = Response(config.data)
        response["Cache-Control"] = f"public, max-age={PUBLIC_CACHE_SECONDS}"
        return response


class ExtensionReportView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "extension_reports"

    def post(self, request):
        serializer = ReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        for anchor in set(data["anchors"]):
            report, _ = ExtensionReport.objects.get_or_create(
                version=data["version"], page=data["page"], anchor=anchor
            )
            ExtensionReport.objects.filter(pk=report.pk).update(
                count=F("count") + 1, last_seen=timezone.now()
            )
        return Response(status=204)
