from django.contrib import admin
from django.utils import timezone
from rest_framework_api_key.admin import APIKeyModelAdmin

from apikeys.models import APIAccessRequest, ClientAPIKey


@admin.register(ClientAPIKey)
class ClientAPIKeyAdmin(APIKeyModelAdmin):
    list_display = (*APIKeyModelAdmin.list_display, "tier", "user")
    list_filter = (*APIKeyModelAdmin.list_filter, "tier")
    search_fields = ("prefix", "name", "user__username", "user__email")


@admin.register(APIAccessRequest)
class APIAccessRequestAdmin(admin.ModelAdmin):
    list_display = ("app_name", "user", "status", "created", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("app_name", "user__username", "user__email", "contact_email")
    readonly_fields = ("created", "reviewed_at", "reviewer")
    actions = ("approve_requests", "reject_requests")

    @admin.action(description="Approve selected requests")
    def approve_requests(self, request, queryset) -> None:
        updated = queryset.update(
            status=APIAccessRequest.Status.APPROVED,
            reviewed_at=timezone.now(),
            reviewer=request.user,
        )
        self.message_user(request, f"{updated} request(s) approved.")

    @admin.action(description="Reject selected requests")
    def reject_requests(self, request, queryset) -> None:
        updated = queryset.update(
            status=APIAccessRequest.Status.REJECTED,
            reviewed_at=timezone.now(),
            reviewer=request.user,
        )
        self.message_user(request, f"{updated} request(s) rejected.")
