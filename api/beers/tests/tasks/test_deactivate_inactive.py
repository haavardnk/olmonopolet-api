from datetime import timedelta

import pytest
from beers.models import Beer
from beers.tasks import deactivate_inactive
from django.utils import timezone


@pytest.mark.django_db
def test_deactivate_inactive_beer() -> None:
    """
    Test that a beer which is no longer on vinmonopolet gets deactivated.
    """
    beer = Beer.objects.create(
        vmp_id=12611502,
        vmp_name="Ayinger Winterbock",
        active=True,
        vmp_updated=timezone.now() - timedelta(days=31),
    )
    Beer.objects.filter(pk=beer.pk).update(
        created_at=timezone.now() - timedelta(days=15)
    )

    deactivate_inactive(30)

    beer.refresh_from_db()
    assert not beer.active


@pytest.mark.django_db
def test_new_beer_does_not_get_deactivated() -> None:
    """
    Test that a beer created less than 10 days ago does not get deactivated.
    """
    Beer.objects.create(
        vmp_id=12611502,
        vmp_name="Ayinger Winterbock",
        active=True,
        vmp_updated=timezone.now() - timedelta(days=31),
    )

    deactivate_inactive(30)

    beer = Beer.objects.get(vmp_id=12611502)
    assert beer.active


@pytest.mark.django_db
def test_active_beer_does_not_get_deactivated() -> None:
    """
    Test that a beer which is active on vinmonopolet does not get deactivated.
    """
    Beer.objects.create(
        vmp_id=12611502,
        vmp_name="Ayinger Winterbock",
        active=True,
        vmp_updated=timezone.now() - timedelta(days=29),
    )

    deactivate_inactive(30)

    beer = Beer.objects.get(vmp_id=12611502)
    assert beer.active
