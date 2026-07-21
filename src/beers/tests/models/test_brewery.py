import pytest
from beers.tests.factories import BreweryFactory


@pytest.mark.django_db
class TestBreweryStr:
    def test_str_returns_name(self) -> None:
        brewery = BreweryFactory(name="Lervig")
        assert str(brewery) == "Lervig"

    def test_str_falls_back_to_url(self) -> None:
        brewery = BreweryFactory(name=None, untpd_url="https://untappd.com/Lervig")
        assert str(brewery) == "https://untappd.com/Lervig"
