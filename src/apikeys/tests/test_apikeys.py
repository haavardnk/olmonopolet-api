import pytest
from beers.tests.factories import UserFactory
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apikeys.models import APIAccessRequest, ClientAPIKey
from apikeys.permissions import HasClientAPIKey, IsAuthenticatedOrHasAPIKey
from apikeys.throttling import TieredAPIKeyThrottle

factory = APIRequestFactory()
view = APIView()


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()


@pytest.mark.django_db
class TestIsAuthenticatedOrHasAPIKey:
    def test_anonymous_denied(self) -> None:
        request = factory.get("/beers/")
        request.user = AnonymousUser()
        permission = IsAuthenticatedOrHasAPIKey()
        assert not permission.has_permission(request, view)

    def test_valid_key_allowed(self) -> None:
        _, key = ClientAPIKey.objects.create_key(
            name="test", tier=ClientAPIKey.Tier.FREE
        )
        request = factory.get("/beers/", HTTP_X_API_KEY=key)
        request.user = AnonymousUser()
        permission = IsAuthenticatedOrHasAPIKey()
        assert permission.has_permission(request, view)

    def test_invalid_key_denied(self) -> None:
        request = factory.get("/beers/", HTTP_X_API_KEY="not.a.real.key")
        permission = HasClientAPIKey()
        assert not permission.has_permission(request, view)

    def test_authenticated_user_allowed(self) -> None:
        user = UserFactory()
        request = factory.get("/beers/")
        request.user = user
        permission = IsAuthenticatedOrHasAPIKey()
        assert permission.has_permission(request, view)


@pytest.mark.django_db
class TestTieredAPIKeyThrottle:
    def test_no_key_bypasses(self) -> None:
        request = factory.get("/beers/")
        request.user = UserFactory()
        throttle = TieredAPIKeyThrottle()
        assert throttle.allow_request(request, view)

    def test_free_tier_rate_limited(self) -> None:
        _, key = ClientAPIKey.objects.create_key(
            name="test", tier=ClientAPIKey.Tier.FREE
        )
        request = factory.get("/beers/", HTTP_X_API_KEY=key)
        throttle = TieredAPIKeyThrottle()
        throttle.THROTTLE_RATES = {"apikey_free": "2/min"}
        assert throttle.allow_request(request, view)
        assert throttle.allow_request(request, view)
        assert not throttle.allow_request(request, view)

    def test_internal_tier_unlimited(self) -> None:
        _, key = ClientAPIKey.objects.create_key(
            name="internal", tier=ClientAPIKey.Tier.INTERNAL
        )
        request = factory.get("/beers/", HTTP_X_API_KEY=key)
        throttle = TieredAPIKeyThrottle()
        assert all(throttle.allow_request(request, view) for _ in range(50))


@pytest.mark.django_db
class TestAPIAccessRequest:
    def test_defaults_to_pending(self) -> None:
        user = UserFactory()
        access_request = APIAccessRequest.objects.create(
            user=user,
            app_name="My App",
            description="A cool app",
            intended_use="Show beers",
            contact_email="dev@example.com",
        )
        assert access_request.status == APIAccessRequest.Status.PENDING
        assert access_request.reviewed_at is None
