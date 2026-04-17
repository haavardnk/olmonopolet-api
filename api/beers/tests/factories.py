import factory
from beers.models import Beer, Country, Stock, Store
from django.contrib.auth.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@test.com")


class CountryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Country

    name = factory.Sequence(lambda n: f"Country {n}")
    iso_code = None


class BeerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Beer

    vmp_id = factory.Sequence(lambda n: 10000000 + n)
    vmp_name = factory.Sequence(lambda n: f"Test Beer {n}")


class StoreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Store

    store_id = factory.Sequence(lambda n: 100 + n)
    name = factory.Sequence(lambda n: f"Store {n}")
    address = factory.Sequence(lambda n: f"Address {n}")
    zipcode = 1234
    area = "Test Area"
    category = "Kategori 4"
    gps_lat = 59.9
    gps_long = 10.7


class StockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Stock

    store = factory.SubFactory(StoreFactory)
    beer = factory.SubFactory(BeerFactory)
    quantity = 10
