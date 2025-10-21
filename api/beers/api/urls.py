from beers.api.views import (
    BeerViewSet,
    ReleaseViewSet,
    StockChangeViewSet,
    StockViewSet,
    StoreViewSet,
    WrongMatchViewSet,
)
from django.conf import settings
from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("beers", BeerViewSet, basename="beer")
router.register("stores", StoreViewSet, basename="store")
router.register("stock", StockViewSet, basename="stock")
router.register("stockchange", StockChangeViewSet, basename="stockchange")
router.register("release", ReleaseViewSet, basename="release")
router.register("wrongmatch", WrongMatchViewSet, basename="wrongmatch")

urlpatterns = [
    path("", include(router.urls)),
]
