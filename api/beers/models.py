import uuid

import requests
from dirtyfields import DirtyFieldsMixin
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.db.models.deletion import CASCADE


class Option(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    active = models.BooleanField()

    def __str__(self):
        return self.name


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True, primary_key=True)
    iso_code = models.CharField(max_length=2, blank=True, null=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Countries"

    def __str__(self):
        return f"{self.name}"


class Beer(DirtyFieldsMixin, models.Model):
    # Vinmonopolet info
    vmp_id = models.BigIntegerField(primary_key=True)
    vmp_name = models.CharField(max_length=150)
    main_category = models.CharField(max_length=50, blank=True, null=True)
    sub_category = models.CharField(max_length=50, blank=True, null=True)
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, blank=True, null=True, related_name="beers"
    )
    price = models.FloatField(blank=True, null=True)
    volume = models.FloatField(blank=True, null=True)
    price_per_volume = models.FloatField(blank=True, null=True)
    product_selection = models.CharField(max_length=50, default="Tilleggsutvalget")
    vmp_url = models.CharField(
        max_length=250, validators=[URLValidator()], blank=True, null=True
    )
    post_delivery = models.BooleanField(blank=True, null=True)
    store_delivery = models.BooleanField(blank=True, null=True)

    # Vinmonopolet detailed info
    year = models.IntegerField(blank=True, null=True)
    fullness = models.IntegerField(blank=True, null=True)
    sweetness = models.IntegerField(blank=True, null=True)
    freshness = models.IntegerField(blank=True, null=True)
    bitterness = models.IntegerField(blank=True, null=True)
    sugar = models.FloatField(blank=True, null=True)
    acid = models.FloatField(blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    aroma = models.CharField(max_length=100, blank=True, null=True)
    taste = models.CharField(max_length=100, blank=True, null=True)
    storable = models.CharField(max_length=100, blank=True, null=True)
    food_pairing = models.CharField(max_length=100, blank=True, null=True)
    raw_materials = models.CharField(max_length=150, blank=True, null=True)
    allergens = models.CharField(max_length=100, blank=True, null=True)
    method = models.CharField(max_length=250, blank=True, null=True)

    # Untappd info
    untpd_id = models.IntegerField(blank=True, null=True)
    untpd_name = models.CharField(max_length=200, blank=True, null=True)
    untpd_url = models.CharField(
        max_length=250, validators=[URLValidator()], blank=True, null=True
    )
    verified_match = models.BooleanField(default=False)
    match_manually = models.BooleanField(default=False)
    prioritize_recheck = models.BooleanField(default=False)
    brewery = models.CharField(max_length=100, blank=True, null=True)
    rating = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(5)], blank=True, null=True
    )
    checkins = models.IntegerField(blank=True, null=True)
    style = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    abv = models.FloatField(blank=True, null=True)
    ibu = models.IntegerField(blank=True, null=True)
    label_hd_url = models.CharField(
        max_length=250, validators=[URLValidator()], blank=True, null=True
    )
    label_sm_url = models.CharField(
        max_length=250, validators=[URLValidator()], blank=True, null=True
    )

    # Calculated info
    alcohol_units = models.FloatField(blank=True, null=True)
    price_per_alcohol_unit = models.FloatField(blank=True, null=True)

    # Classification
    is_christmas_beer = models.BooleanField(default=False)

    # Server update times
    vmp_updated = models.DateTimeField(blank=True, null=True)
    vmp_details_fetched = models.DateTimeField(blank=True, null=True)
    untpd_updated = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    @property
    def value_score(self) -> float | None:
        if (
            self.rating
            and self.rating > 0
            and self.price_per_volume
            and self.price_per_volume > 0
        ):
            return (
                (self.rating**4.8) / ((self.price_per_volume / 100) ** 0.32)
            ) * 0.0176
        return None

    def __str__(self):
        return self.vmp_name

    def save(self, *args, **kwargs):
        try:
            dirty_fields = self.get_dirty_fields()
            if (
                "untpd_url" in dirty_fields
                and len(dirty_fields) == 1
                and self.untpd_url is not None
                and self.untpd_id != self.untpd_url.split("/")[-1]
            ):
                self.untpd_id = self.untpd_url.split("/")[-1]
                self.prioritize_recheck = True
                self.verified_match = True
                self.match_manually = False
                self.save()

            if (
                "match_manually" in dirty_fields
                and len(dirty_fields) == 1
                and self.match_manually
            ):
                self.untpd_id = None
                self.untpd_name = None
                self.untpd_url = None
                self.verified_match = False
                self.prioritize_recheck = False
                self.brewery = None
                self.rating = None
                self.checkins = None
                self.style = None
                self.description = None
                self.abv = None
                self.ibu = None
                self.label_hd_url = None
                self.label_sm_url = None
                self.alcohol_units = None
                self.untpd_updated = None
                self.save()

        except Exception as error:
            print(error)

        super(Beer, self).save(*args, **kwargs)


class Store(models.Model):
    store_id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    zipcode = models.IntegerField()
    area = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    gps_lat = models.FloatField()
    gps_long = models.FloatField()

    store_updated = models.DateTimeField(auto_now=True)
    store_stock_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Stock(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    beer = models.ForeignKey(Beer, on_delete=models.CASCADE)
    quantity = models.IntegerField()

    stock_updated = models.DateTimeField(auto_now=True)
    stocked_at = models.DateTimeField(blank=True, null=True)
    unstocked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = [["store", "beer"]]

    def __str__(self):
        return self.beer.vmp_name


class WrongMatch(models.Model):
    beer = models.ForeignKey(Beer, on_delete=models.CASCADE)
    suggested_url = models.CharField(max_length=250, validators=[URLValidator()])
    accept_change = models.BooleanField(default=False)

    def __str__(self):
        return self.beer.vmp_name

    def save(self, *args, **kwargs):
        super(WrongMatch, self).save(*args, **kwargs)

        if "https://untp.beer/" in self.suggested_url:
            try:
                suggested_url = requests.head(self.suggested_url).headers["location"]
            except Exception:
                suggested_url = self.suggested_url
        else:
            suggested_url = self.suggested_url

        try:
            auto_accept = Option.objects.get(name="auto_accept_wrong_match").active
            if auto_accept:
                self.accept_change = auto_accept
        except Option.DoesNotExist:
            pass

        if self.accept_change and suggested_url != self.beer.untpd_url:
            self.beer.untpd_url = suggested_url
            self.beer.untpd_id = int(suggested_url.split("/")[-1])
            self.beer.prioritize_recheck = True
            self.beer.verified_match = True
            self.beer.match_manually = False
            self.beer.save()

            self.delete()

        elif self.accept_change and suggested_url == self.beer.untpd_url:
            self.delete()


class ExternalAPI(models.Model):
    name = models.CharField(primary_key=True, max_length=50)
    baseurl = models.TextField(validators=[URLValidator()])
    api_client_id = models.CharField(max_length=100, blank=True, null=True)
    api_client_secret = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name


class VmpNotReleased(models.Model):
    id = models.IntegerField(primary_key=True)


class Badge(models.Model):
    beer = models.ForeignKey(Beer, on_delete=CASCADE)
    text = models.CharField(max_length=100)
    type = models.CharField(max_length=50)

    def __str__(self):
        return self.text + " - " + self.beer.vmp_name


class Release(models.Model):
    name = models.CharField(max_length=50, primary_key=True, unique=True)
    beer = models.ManyToManyField(Beer)
    active = models.BooleanField(default=True)
    release_date = models.DateTimeField(blank=True, null=True)
    product_selection = models.CharField(max_length=150, blank=True, null=True)
    is_christmas_release = models.BooleanField(default=False)


class Tasted(models.Model):
    user = models.ForeignKey("auth.User", on_delete=CASCADE)
    beer = models.ForeignKey(Beer, on_delete=CASCADE)
    rating = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(5)], blank=True, null=True
    )

    class Meta:
        unique_together = ["user", "beer"]
        indexes = [
            models.Index(fields=["user", "beer"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.beer.vmp_name}"


class UserList(models.Model):
    user = models.ForeignKey("auth.User", on_delete=CASCADE, related_name="lists")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class UserListItem(models.Model):
    list = models.ForeignKey(UserList, on_delete=CASCADE, related_name="items")
    product_id = models.CharField(max_length=50)
    position = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["list", "product_id"]
        ordering = ["position", "added_at"]

    def __str__(self):
        return f"{self.list.name} - {self.product_id}"
