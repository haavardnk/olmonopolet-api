from django.contrib import admin
from django.urls import include, path, re_path

urlpatterns = [
    re_path(r"^admin/shell/", include("django_admin_shell.urls")),
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    path("", include("beers.api.urls")),
]
