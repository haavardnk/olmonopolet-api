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

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

router.register(r"beers", BeerViewSet, basename="beer")
router.register(r"stores", StoreViewSet, basename="store")
router.register(r"stock", StockViewSet, basename="stock")
router.register(r"wrongmatch", WrongMatchViewSet, basename="wrongmatch")
router.register(r"release", ReleaseViewSet, basename="release")
router.register(r"stockchange", StockChangeViewSet, basename="stockchange")

urlpatterns = [
    path("", include(router.urls)),
]
