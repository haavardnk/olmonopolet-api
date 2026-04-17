import pytest
from beers.api.filters import BeerFilter, NullsAlwaysLastOrderingFilter
from beers.models import Beer
from beers.tests.factories import BeerFactory, StockFactory, StoreFactory
from django.test import RequestFactory
from rest_framework.request import Request


@pytest.mark.django_db
class TestStoreFilter:
    def test_single_store_with_stock(self) -> None:
        store = StoreFactory(store_id=100)
        beer_stocked = BeerFactory()
        beer_unstocked = BeerFactory()
        StockFactory(store=store, beer=beer_stocked, quantity=5)
        StockFactory(store=store, beer=beer_unstocked, quantity=0)

        f = BeerFilter()
        result = f.custom_store_filter(Beer.objects.all(), "store", "100")
        pks = list(result.values_list("pk", flat=True))

        assert beer_stocked.pk in pks
        assert beer_unstocked.pk not in pks

    def test_comma_separated_stores(self) -> None:
        store1 = StoreFactory(store_id=200)
        store2 = StoreFactory(store_id=201)
        beer1 = BeerFactory()
        beer2 = BeerFactory()
        StockFactory(store=store1, beer=beer1, quantity=3)
        StockFactory(store=store2, beer=beer2, quantity=7)

        f = BeerFilter()
        result = f.custom_store_filter(Beer.objects.all(), "store", "200,201")
        pks = list(result.values_list("pk", flat=True))

        assert beer1.pk in pks
        assert beer2.pk in pks

    def test_non_digit_store_id_returns_all(self) -> None:
        BeerFactory()

        f = BeerFilter()
        result = f.custom_store_filter(Beer.objects.all(), "store", "abc")

        assert result.count() == Beer.objects.count()


@pytest.mark.django_db
class TestAllergenFilter:
    def test_exclude_single_allergen(self) -> None:
        beer_gluten = BeerFactory(allergens="Gluten")
        beer_none = BeerFactory(allergens=None)

        f = BeerFilter()
        result = f.custom_allergen_filter(Beer.objects.all(), "exclude_allergen", "Gluten")
        pks = list(result.values_list("pk", flat=True))

        assert beer_gluten.pk not in pks
        assert beer_none.pk in pks

    def test_exclude_multiple_allergens(self) -> None:
        beer_gluten = BeerFactory(allergens="Gluten")
        beer_milk = BeerFactory(allergens="Melk")
        beer_clean = BeerFactory(allergens=None)

        f = BeerFilter()
        result = f.custom_allergen_filter(
            Beer.objects.all(), "exclude_allergen", "Gluten,Melk"
        )
        pks = list(result.values_list("pk", flat=True))

        assert beer_gluten.pk not in pks
        assert beer_milk.pk not in pks
        assert beer_clean.pk in pks

    def test_beer_with_combined_allergens(self) -> None:
        beer_both = BeerFactory(allergens="Melk, Gluten")
        beer_clean = BeerFactory(allergens=None)

        f = BeerFilter()
        result = f.custom_allergen_filter(Beer.objects.all(), "exclude_allergen", "Gluten")
        pks = list(result.values_list("pk", flat=True))

        assert beer_both.pk not in pks
        assert beer_clean.pk in pks


@pytest.mark.django_db
class TestNullsAlwaysLastOrderingFilter:
    def _make_request(self, ordering: str) -> Request:
        django_request = RequestFactory().get(f"/?ordering={ordering}")
        return Request(django_request)

    def test_ascending_nulls_last(self) -> None:
        beer_low = BeerFactory(rating=3.0)
        beer_high = BeerFactory(rating=4.0)
        beer_null = BeerFactory(rating=None)

        ordering_filter = NullsAlwaysLastOrderingFilter()

        class FakeView:
            ordering_fields = ["rating"]

        request = self._make_request("rating")
        result = ordering_filter.filter_queryset(
            request, Beer.objects.all(), FakeView()
        )
        pks = list(result.values_list("pk", flat=True))

        assert pks == [beer_low.pk, beer_high.pk, beer_null.pk]

    def test_descending_nulls_last(self) -> None:
        beer_low = BeerFactory(rating=3.0)
        beer_high = BeerFactory(rating=4.0)
        beer_null = BeerFactory(rating=None)

        ordering_filter = NullsAlwaysLastOrderingFilter()

        class FakeView:
            ordering_fields = ["rating"]

        request = self._make_request("-rating")
        result = ordering_filter.filter_queryset(
            request, Beer.objects.all(), FakeView()
        )
        pks = list(result.values_list("pk", flat=True))

        assert pks == [beer_high.pk, beer_low.pk, beer_null.pk]

    def test_ppau_ordering_excludes_low_abv(self) -> None:
        beer_low_abv = BeerFactory(abv=0.5, price_per_alcohol_unit=10.0)
        beer_high_abv = BeerFactory(abv=5.0, price_per_alcohol_unit=5.0)

        ordering_filter = NullsAlwaysLastOrderingFilter()

        class FakeView:
            ordering_fields = ["price_per_alcohol_unit"]

        request = self._make_request("price_per_alcohol_unit")
        result = ordering_filter.filter_queryset(
            request, Beer.objects.all(), FakeView()
        )
        pks = list(result.values_list("pk", flat=True))

        assert beer_high_abv.pk in pks
        assert beer_low_abv.pk not in pks
