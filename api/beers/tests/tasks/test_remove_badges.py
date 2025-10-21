import pytest
from beers.models import Badge, Beer
from beers.tasks import remove_badges


@pytest.mark.django_db
def test_remove_badges():
    """
    Test that a badges gets removed, and only the correct badges.
    """
    beer = Beer.objects.create(
        vmp_id=12611502,
        vmp_name="Ayinger Winterbock",
        active=True,
    )
    Badge.objects.create(beer=beer, text="test1", type="badge1")
    Badge.objects.create(beer=beer, text="test2", type="badge2")

    remove_badges("badge1")

    with pytest.raises(Badge.DoesNotExist):
        Badge.objects.get(type="badge1")

    assert Badge.objects.get(type="badge2")
