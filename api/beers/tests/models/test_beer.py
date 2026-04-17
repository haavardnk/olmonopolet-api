import pytest
import responses
from beers.models import Beer, Option, WrongMatch
from beers.tests.factories import BeerFactory


class TestValueScore:
    def test_normal_values(self) -> None:
        beer = BeerFactory.build(rating=4.0, price_per_volume=300.0)
        expected = (4.0**4.8) / ((300.0 / 100) ** 0.32) * 0.0176
        assert beer.value_score == pytest.approx(expected)

    def test_rating_zero_returns_none(self) -> None:
        beer = BeerFactory.build(rating=0, price_per_volume=300.0)
        assert beer.value_score is None

    def test_null_rating_returns_none(self) -> None:
        beer = BeerFactory.build(rating=None, price_per_volume=300.0)
        assert beer.value_score is None

    def test_null_ppv_returns_none(self) -> None:
        beer = BeerFactory.build(rating=4.0, price_per_volume=None)
        assert beer.value_score is None

    def test_both_null_returns_none(self) -> None:
        beer = BeerFactory.build(rating=None, price_per_volume=None)
        assert beer.value_score is None

    def test_high_rating_low_ppv(self) -> None:
        beer = BeerFactory.build(rating=4.5, price_per_volume=100.0)
        expected = (4.5**4.8) / ((100.0 / 100) ** 0.32) * 0.0176
        assert beer.value_score == pytest.approx(expected)


@pytest.mark.django_db
class TestBeerSaveUntpdUrlCascade:
    def test_setting_untpd_url_extracts_id(self) -> None:
        beer = BeerFactory()
        beer.untpd_url = "https://untappd.com/beer/12345"
        beer.save()
        beer.refresh_from_db()

        assert beer.untpd_id == 12345
        assert beer.verified_match is True
        assert beer.prioritize_recheck is True
        assert beer.match_manually is False

    def test_setting_url_to_none_skips_cascade(self) -> None:
        beer = BeerFactory(untpd_id=999, untpd_url="https://untappd.com/beer/999")
        beer.untpd_url = None
        beer.save()
        beer.refresh_from_db()

        assert beer.untpd_id == 999

    def test_changing_url_updates_id(self) -> None:
        beer = BeerFactory(untpd_id=111, untpd_url="https://untappd.com/beer/111")
        beer.untpd_url = "https://untappd.com/beer/222"
        beer.save()
        beer.refresh_from_db()

        assert beer.untpd_id == 222
        assert beer.verified_match is True


@pytest.mark.django_db
class TestBeerSaveMatchManuallyCascade:
    def test_setting_match_manually_clears_untappd_fields(self) -> None:
        beer = BeerFactory(
            untpd_id=123,
            untpd_name="Test Untappd",
            untpd_url="https://untappd.com/beer/123",
            verified_match=True,
            brewery="Test Brewery",
            rating=4.2,
            checkins=500,
            style="IPA",
            description="A hoppy beer",
            abv=6.5,
            ibu=60,
            label_hd_url="https://example.com/hd.png",
            label_sm_url="https://example.com/sm.png",
            alcohol_units=2.0,
        )
        beer.match_manually = True
        beer.save()
        beer.refresh_from_db()

        assert beer.untpd_id is None
        assert beer.untpd_name is None
        assert beer.untpd_url is None
        assert beer.verified_match is False
        assert beer.prioritize_recheck is False
        assert beer.brewery is None
        assert beer.rating is None
        assert beer.checkins is None
        assert beer.style is None
        assert beer.description is None
        assert beer.abv is None
        assert beer.ibu is None
        assert beer.label_hd_url is None
        assert beer.label_sm_url is None
        assert beer.alcohol_units is None
        assert beer.untpd_updated is None

    def test_setting_match_manually_false_no_cascade(self) -> None:
        beer = BeerFactory(
            match_manually=True,
            untpd_id=None,
            rating=None,
        )
        beer.match_manually = False
        beer.save()
        beer.refresh_from_db()

        assert beer.match_manually is False


@pytest.mark.django_db
class TestWrongMatchSave:
    def test_auto_accept_updates_beer_and_deletes(self) -> None:
        Option.objects.create(name="auto_accept_wrong_match", active=True)
        beer = BeerFactory(untpd_url=None, untpd_id=None)
        wm = WrongMatch(
            beer=beer,
            suggested_url="https://untappd.com/beer/99999",
        )
        wm.save()

        beer.refresh_from_db()
        assert beer.untpd_id == 99999
        assert beer.untpd_url == "https://untappd.com/beer/99999"
        assert beer.verified_match is True
        with pytest.raises(WrongMatch.DoesNotExist):
            WrongMatch.objects.get(pk=wm.pk)

    def test_accept_same_url_just_deletes(self) -> None:
        url = "https://untappd.com/beer/55555"
        beer = BeerFactory(untpd_url=url, untpd_id=55555)
        wm = WrongMatch.objects.create(
            beer=beer,
            suggested_url=url,
            accept_change=True,
        )

        with pytest.raises(WrongMatch.DoesNotExist):
            WrongMatch.objects.get(pk=wm.pk)

    def test_no_accept_persists(self) -> None:
        beer = BeerFactory()
        wm = WrongMatch.objects.create(
            beer=beer,
            suggested_url="https://untappd.com/beer/77777",
            accept_change=False,
        )

        assert WrongMatch.objects.filter(pk=wm.pk).exists()

    @responses.activate
    def test_short_url_expansion(self) -> None:
        Option.objects.create(name="auto_accept_wrong_match", active=True)
        expanded = "https://untappd.com/beer/77777"
        responses.add(
            responses.HEAD,
            "https://untp.beer/abc",
            headers={"location": expanded},
            status=301,
        )

        beer = BeerFactory(untpd_url=None, untpd_id=None)
        wm = WrongMatch(
            beer=beer,
            suggested_url="https://untp.beer/abc",
        )
        wm.save()

        beer.refresh_from_db()
        assert beer.untpd_url == expanded
        assert beer.untpd_id == 77777
