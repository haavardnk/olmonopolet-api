from django.urls import path

from extension.views import ExtensionConfigView, ExtensionReportView

urlpatterns = [
    path("extension/config/", ExtensionConfigView.as_view(), name="extension-config"),
    path("extension/reports/", ExtensionReportView.as_view(), name="extension-reports"),
]
