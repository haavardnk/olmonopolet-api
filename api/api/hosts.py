from django.conf import settings
from django_hosts import host, patterns

host_patterns = patterns(
    "",
    host("api", settings.ROOT_URLCONF, name="api"),
    host("auth", "accounts.urls", name="auth"),
)
