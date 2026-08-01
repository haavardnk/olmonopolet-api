from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from beers.models import Beer, Stock, Tasted
from beers.tests.factories import BeerFactory, StockFactory, UserFactory


@pytest.mark.django_db
class TestBeerQuerySetWithUserTasted:
    def test_annotates_true_for_tasted_beers(self) -> None:
        user = UserFactory()
        tasted = BeerFactory()
        untasted = BeerFactory()
        Tasted.objects.create(user=user, beer=tasted)

        results = {
            beer.pk: beer.user_tasted for beer in Beer.objects.with_user_tasted(user)
        }

        assert results[tasted.pk] is True
        assert results[untasted.pk] is False

    @pytest.mark.parametrize("user", [None, AnonymousUser()])
    def test_annotates_false_without_user(self, user: AnonymousUser | None) -> None:
        beer = BeerFactory()

        assert Beer.objects.with_user_tasted(user).get(pk=beer.pk).user_tasted is False


@pytest.mark.django_db
class TestStockQuerySetStockChanges:
    def test_excludes_unchanged_stock(self) -> None:
        StockFactory()
        changed = StockFactory(stocked_at=timezone.now())

        assert [stock.pk for stock in Stock.objects.stock_changes()] == [changed.pk]

    def test_orders_newest_change_first(self) -> None:
        now = timezone.now()
        older = StockFactory(stocked_at=now - timedelta(days=2))
        newer = StockFactory(unstocked_at=now)

        assert [stock.pk for stock in Stock.objects.stock_changes()] == [
            newer.pk,
            older.pk,
        ]
