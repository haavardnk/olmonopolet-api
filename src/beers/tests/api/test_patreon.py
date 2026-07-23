import pytest
import responses
from beers.models import Option
from beers.patreon import (
    POSTS_URL,
    TOKEN_URL,
    fetch_patreon_posts,
)
from rest_framework.test import APIClient

CAMPAIGN_ID = "camp1"
POSTS_ENDPOINT = POSTS_URL.format(campaign_id=CAMPAIGN_ID)

TOKEN_BODY = {
    "access_token": "new-access",
    "refresh_token": "new-refresh",
    "expires_in": 2678400,
}

POSTS_BODY = {
    "data": [
        {
            "id": "1",
            "type": "post",
            "attributes": {
                "title": "Public",
                "content": "c",
                "url": "/posts/1",
                "published_at": "2026-07-01T00:00:00.000+00:00",
                "is_public": True,
            },
        },
        {
            "id": "2",
            "type": "post",
            "attributes": {
                "title": "Private",
                "content": "c",
                "url": "/posts/2",
                "published_at": "2026-07-02T00:00:00.000+00:00",
                "is_public": False,
            },
        },
    ]
}


@pytest.fixture(autouse=True)
def _patreon_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATREON_CLIENT_ID", "client-id")
    monkeypatch.setenv("PATREON_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("PATREON_CAMPAIGN_ID", CAMPAIGN_ID)
    monkeypatch.setenv("PATREON_REFRESH_TOKEN", "bootstrap-refresh")


@pytest.mark.django_db
class TestFetchPatreonPosts:
    @responses.activate
    def test_returns_public_posts_and_persists_rotated_token(self) -> None:
        responses.add(responses.POST, TOKEN_URL, json=TOKEN_BODY, status=200)
        responses.add(responses.GET, POSTS_ENDPOINT, json=POSTS_BODY, status=200)

        posts = fetch_patreon_posts()

        assert [post["id"] for post in posts] == ["1"]
        assert posts[0]["url"] == "https://www.patreon.com/posts/1"
        assert Option.objects.get(name="patreon_refresh_token").value == "new-refresh"
        assert Option.objects.get(name="patreon_access_token").value == "new-access"

    @responses.activate
    def test_caches_posts_after_first_fetch(self) -> None:
        responses.add(responses.POST, TOKEN_URL, json=TOKEN_BODY, status=200)
        responses.add(responses.GET, POSTS_ENDPOINT, json=POSTS_BODY, status=200)

        fetch_patreon_posts()
        posts = fetch_patreon_posts()

        assert [post["id"] for post in posts] == ["1"]
        assert len(responses.calls) == 2

    @responses.activate
    def test_refresh_failure_returns_empty(self) -> None:
        responses.add(responses.POST, TOKEN_URL, status=401)

        assert fetch_patreon_posts() == []

    @responses.activate
    def test_force_refresh_on_401(self) -> None:
        Option.objects.create(
            name="patreon_access_token", active=True, value="stale-access"
        )
        Option.objects.create(
            name="patreon_access_token_expires", active=True, value="9999999999"
        )
        responses.add(responses.GET, POSTS_ENDPOINT, status=401)
        responses.add(responses.POST, TOKEN_URL, json=TOKEN_BODY, status=200)
        responses.add(responses.GET, POSTS_ENDPOINT, json=POSTS_BODY, status=200)

        posts = fetch_patreon_posts()

        assert [post["id"] for post in posts] == ["1"]
        assert Option.objects.get(name="patreon_access_token").value == "new-access"


@pytest.mark.django_db
class TestPatreonPostsView:
    @responses.activate
    def test_endpoint_returns_public_posts(self) -> None:
        responses.add(responses.POST, TOKEN_URL, json=TOKEN_BODY, status=200)
        responses.add(responses.GET, POSTS_ENDPOINT, json=POSTS_BODY, status=200)

        response = APIClient().get("/patreon/posts/")

        assert response.status_code == 200
        assert [post["id"] for post in response.data] == ["1"]
        assert "max-age" in response["Cache-Control"]
