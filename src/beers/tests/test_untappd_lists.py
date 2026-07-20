import pytest
import responses
from beers.untappd_lists import (
    UNTAPPD_BASE,
    UntappdCookieExpired,
    _parse_user_lists_page,
    fetch_user_lists,
)
from bs4 import BeautifulSoup

LISTS_HTML = """
<div class="single-list">
  <a href="/user/testuser/lists/12345"><h2>My Cellar</h2></a>
  <h4>7 Items</h4>
</div>
<div class="single-list">
  <a href="/user/testuser/wishlist"><h2>Wish List</h2></a>
  <h4>3 Items</h4>
</div>
"""

LOGIN_HTML = '<form action="login" method="post"></form>'


class TestParseUserListsPage:
    def test_parses_custom_list_and_wishlist(self) -> None:
        soup = BeautifulSoup(LISTS_HTML, "html.parser")
        lists = _parse_user_lists_page(soup)
        assert [(item.list_id, item.name, item.item_count) for item in lists] == [
            (12345, "My Cellar", 7),
            (0, "Wish List", 3),
        ]


class TestFetchUserLists:
    @pytest.fixture(autouse=True)
    def _no_cookie_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "beers.untappd_lists._inject_session_cookies", lambda scraper: None
        )

    @responses.activate
    def test_returns_custom_list_and_wishlist(self) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/user/testuser/lists",
            body=LISTS_HTML,
            status=200,
        )
        lists = fetch_user_lists("testuser")
        assert [item.list_id for item in lists] == [12345, 0]

    @responses.activate
    def test_login_redirect_raises_cookie_expired(self) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/user/testuser/lists",
            body=LOGIN_HTML,
            status=200,
        )
        with pytest.raises(UntappdCookieExpired):
            fetch_user_lists("testuser")

    @responses.activate
    def test_missing_user_raises_value_error(self) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/user/nope/lists",
            status=404,
        )
        with pytest.raises(ValueError):
            fetch_user_lists("nope")
