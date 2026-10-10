from django.core.exceptions import ValidationError
from django.db import models


class ExtensionConfig(models.Model):
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self) -> None:
        if not isinstance(self.data, dict) or not isinstance(
            self.data.get("schema"), int
        ):
            raise ValidationError(
                {"data": "Config must be an object with an integer 'schema'"}
            )

    def __str__(self) -> str:
        return f"Extension config {self.updated_at:%Y-%m-%d %H:%M}"


class ExtensionReport(models.Model):
    version = models.CharField(max_length=20)
    page = models.CharField(max_length=20)
    anchor = models.CharField(max_length=50)
    count = models.PositiveIntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "page", "anchor"], name="unique_extension_report"
            )
        ]

    def __str__(self) -> str:
        return f"{self.version} {self.page} {self.anchor}"
