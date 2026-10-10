from django.contrib import admin

from extension.models import ExtensionConfig, ExtensionReport


@admin.register(ExtensionConfig)
class ExtensionConfigAdmin(admin.ModelAdmin):
    list_display = ("__str__", "updated_at")


@admin.register(ExtensionReport)
class ExtensionReportAdmin(admin.ModelAdmin):
    list_display = ("anchor", "page", "version", "count", "first_seen", "last_seen")
    list_filter = ("page", "version")
    search_fields = ("anchor",)
    readonly_fields = ("version", "page", "anchor", "count", "first_seen", "last_seen")
