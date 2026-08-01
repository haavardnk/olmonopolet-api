import pytest
from beers.management.commands.update_beers_from_untappd import Command
from beers.models import Brewery
from beers.tests.factories import BeerFactory
from clients.untappd import parsers

BREWERY_HTML = """
<p class="brewery"><a href="/LervigAktiebryggeri">Lervig</a></p>
"""

NO_ANCHOR_HTML = '<p class="brewery"></p>'

BREWERY_URL = "https://untappd.com/LervigAktiebryggeri"


@pytest.mark.django_db
class TestLinkBrewery:
    def test_creates_and_links_brewery(self) -> None:
        beer = BeerFactory()

        Command()._link_brewery(beer, parsers.parse_beer(BREWERY_HTML))

        brewery = Brewery.objects.get(untpd_url=BREWERY_URL)
        assert brewery.name == "Lervig"
        assert beer.brewery == brewery

    def test_reuses_existing_brewery(self) -> None:
        beer = BeerFactory()
        data = parsers.parse_beer(BREWERY_HTML)

        Command()._link_brewery(beer, data)
        Command()._link_brewery(beer, data)

        assert Brewery.objects.filter(untpd_url=BREWERY_URL).count() == 1

    def test_no_anchor_leaves_brewery_unset(self) -> None:
        beer = BeerFactory()

        Command()._link_brewery(beer, parsers.parse_beer(NO_ANCHOR_HTML))

        assert beer.brewery is None
