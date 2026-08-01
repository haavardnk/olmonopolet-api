import pytest
from beers.management.commands.update_breweries_from_untappd import Command
from beers.tests.factories import BreweryFactory
from clients.untappd import parsers

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
class TestApplyFields:
    def test_parses_json_ld(self) -> None:
        brewery = BreweryFactory(name=None, description=None)

        Command()._apply_fields(brewery, parsers.parse_brewery(BREWERY_LD_HTML))

        assert brewery.name == "Lervig"
        assert brewery.description == "Craft brewery"
        assert brewery.label_url == "https://untappd.com/logos/brewery-12345.jpeg"

    def test_parses_image_object(self) -> None:
        brewery = BreweryFactory(name=None)

        Command()._apply_fields(
            brewery, parsers.parse_brewery(BREWERY_LD_IMAGE_OBJECT_HTML)
        )

        assert brewery.label_url == "https://untappd.com/logos/brewery-12345.jpeg"

    def test_does_not_overwrite_with_empty(self) -> None:
        brewery = BreweryFactory(name="Existing", description="Existing desc")

        Command()._apply_fields(brewery, parsers.parse_brewery(EMPTY_HTML))

        assert brewery.name == "Existing"
        assert brewery.description == "Existing desc"
