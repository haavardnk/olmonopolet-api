import pytest
from beers.management.commands.update_breweries_from_untappd import Command
from beers.tests.factories import BreweryFactory
from bs4 import BeautifulSoup

BREWERY_LD_HTML = """
<script type="application/ld+json">
{"@type": "Brewery", "name": "Lervig", "description": "Craft brewery",
 "image": "https://untappd.com//logos/brewery-12345.jpeg"}
</script>
"""

BREWERY_LD_IMAGE_OBJECT_HTML = """
<script type="application/ld+json">
{"@type": "Brewery", "name": "Lervig",
 "image": {"@type": "ImageObject",
          "contentUrl": "https://untappd.com//logos/brewery-12345.jpeg"}}
</script>
"""

EMPTY_HTML = "<html><body></body></html>"


@pytest.mark.django_db
class TestUpdateBreweryFields:
    def test_parses_json_ld(self) -> None:
        brewery = BreweryFactory(name=None, description=None)
        soup = BeautifulSoup(BREWERY_LD_HTML, "html.parser")

        Command()._update_brewery_fields(brewery, soup)

        assert brewery.name == "Lervig"
        assert brewery.description == "Craft brewery"
        assert brewery.label_url == "https://untappd.com/logos/brewery-12345.jpeg"

    def test_parses_image_object(self) -> None:
        brewery = BreweryFactory(name=None)
        soup = BeautifulSoup(BREWERY_LD_IMAGE_OBJECT_HTML, "html.parser")

        Command()._update_brewery_fields(brewery, soup)

        assert brewery.label_url == "https://untappd.com/logos/brewery-12345.jpeg"

    def test_does_not_overwrite_with_empty(self) -> None:
        brewery = BreweryFactory(name="Existing", description="Existing desc")
        soup = BeautifulSoup(EMPTY_HTML, "html.parser")

        Command()._update_brewery_fields(brewery, soup)

        assert brewery.name == "Existing"
        assert brewery.description == "Existing desc"
