import pytest
import responses
from clients.untappd import (
    UNTAPPD_BASE,
    UntappdClient,
    UntappdCookieExpired,
    UntappdListNotFound,
    generate_query_variations,
)
from requests import Session

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

LIST_PAGE_HTML = """
<a href="/b/brewery-one/111"></a>
<a href="/b/brewery-two/222"></a>
<a href="/b/brewery-two/222"></a>
"""

SEARCH_HTML = """
<div class="beer-item">
  <div class="name">Lervig Hazy IPA</div>
  <a href="/b/lervig-hazy-ipa/555"></a>
</div>
<div class="beer-item">
  <div class="name">Other Beer</div>
  <a href="/b/other-beer/666"></a>
</div>
"""

WISHLIST_PAGE_1 = {
    "data": {
        "total_count": 3,
        "beers": {"items": [{"beer": {"bid": 1}}, {"beer": {"bid": 2}}]},
    }
}
WISHLIST_PAGE_2 = {
    "data": {"total_count": 3, "beers": {"items": [{"beer": {"bid": 3}}]}}
}


@pytest.fixture
def client() -> UntappdClient:
    return UntappdClient(request_delay=0, scraper=Session())


class TestGenerateQueryVariations:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            (
                "Lervig x Cloudwater Big Beer",
                [
                    "Lervig x Cloudwater Big Beer",
                    "Lervig Cloudwater Big Beer",
                    "Lervig Cloudwater Big",
                ],
            ),
            ("One Two", ["One Two"]),
        ],
    )
    def test_variations(self, name: str, expected: list[str]) -> None:
        assert generate_query_variations(name) == expected


class TestSearchBeers:
    @responses.activate
    def test_parses_results(self, client: UntappdClient) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/search",
            body=SEARCH_HTML,
            status=200,
        )
        results = client.search_beers("lervig hazy ipa")
        assert [(item.name, item.untpd_id, item.url) for item in results] == [
            ("Lervig Hazy IPA", 555, f"{UNTAPPD_BASE}/b/lervig-hazy-ipa/555"),
            ("Other Beer", 666, f"{UNTAPPD_BASE}/b/other-beer/666"),
        ]

    @responses.activate
    def test_error_status_returns_empty(self, client: UntappdClient) -> None:
        responses.add(responses.GET, f"{UNTAPPD_BASE}/search", status=503)
        assert client.search_beers("anything") == []


class TestFetchUserLists:
    @responses.activate
    def test_returns_custom_list_and_wishlist(self, client: UntappdClient) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/user/testuser/lists",
            body=LISTS_HTML,
            status=200,
        )
        lists = client.fetch_user_lists("testuser")
        assert [(item.list_id, item.name, item.item_count) for item in lists] == [
            (12345, "My Cellar", 7),
            (0, "Wish List", 3),
        ]

    @responses.activate
    def test_login_redirect_raises_cookie_expired(self, client: UntappdClient) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/user/testuser/lists",
            body=LOGIN_HTML,
            status=200,
        )
        with pytest.raises(UntappdCookieExpired):
            client.fetch_user_lists("testuser")

    @responses.activate
    def test_missing_user_raises_value_error(self, client: UntappdClient) -> None:
        responses.add(responses.GET, f"{UNTAPPD_BASE}/user/nope/lists", status=404)
        with pytest.raises(ValueError):
            client.fetch_user_lists("nope")


class TestFetchListBeerIds:
    @responses.activate
    def test_paginates_until_empty(self, client: UntappdClient) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/user/testuser/lists/1",
            body=LIST_PAGE_HTML,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/profile/more_list_items/testuser/1/2",
            body='<a href="/b/brewery-three/333"></a>',
            status=200,
        )
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/profile/more_list_items/testuser/1/3",
            body="",
            status=200,
        )
        assert client.fetch_list_beer_ids("testuser", 1) == [111, 222, 333]

    @responses.activate
    def test_missing_list_raises(self, client: UntappdClient) -> None:
        responses.add(
            responses.GET, f"{UNTAPPD_BASE}/user/testuser/lists/9", status=404
        )
        with pytest.raises(UntappdListNotFound):
            client.fetch_list_beer_ids("testuser", 9)

    @responses.activate
    def test_wishlist_paginates_until_total(self, client: UntappdClient) -> None:
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/apireqs/userwishlist/testuser/0",
            json=WISHLIST_PAGE_1,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{UNTAPPD_BASE}/apireqs/userwishlist/testuser/2",
            json=WISHLIST_PAGE_2,
            status=200,
        )
        assert client.fetch_list_beer_ids("testuser", 0) == [1, 2, 3]
