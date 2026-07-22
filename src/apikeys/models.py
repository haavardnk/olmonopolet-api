from django.conf import settings
from django.db import models
from rest_framework_api_key.models import AbstractAPIKey


class ClientAPIKey(AbstractAPIKey):
    class Tier(models.TextChoices):
        INTERNAL = "internal", "Internal"
        OFFICIAL = "official", "Official"
        PARTNER = "partner", "Partner"
        FREE = "free", "Free"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="api_keys",
    )
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.FREE)
    purpose = models.TextField(blank=True)

    class Meta(AbstractAPIKey.Meta):
        verbose_name = "Client API key"
        verbose_name_plural = "Client API keys"


class APIAccessRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_access_requests",
    )
    app_name = models.CharField(max_length=100)
    description = models.TextField()
    website = models.URLField(blank=True)
    intended_use = models.TextField()
    contact_email = models.EmailField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_api_requests",
    )

    class Meta:
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.app_name} ({self.user})"
