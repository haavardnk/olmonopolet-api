from rest_framework import permissions
from rest_framework.authtoken.models import Token
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from beers.api.serializers import WrongMatchSerializer
from beers.api.views.base import PUBLIC_CACHE_SECONDS, BrowsableMixin
from beers.models import WrongMatch
from clients.patreon import fetch_patreon_posts


class WrongMatchViewSet(BrowsableMixin, CreateModelMixin, GenericViewSet):
    queryset = WrongMatch.objects.all().select_related("beer")
    serializer_class = WrongMatchSerializer
    permission_classes = [permissions.AllowAny]


class ExtensionTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        token, _ = Token.objects.get_or_create(user=request.user)
        return Response({"token": token.key})

    def post(self, request):
        token, _ = Token.objects.get_or_create(user=request.user)
        return Response({"token": token.key})

    def delete(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=204)


class PatreonPostsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        posts = fetch_patreon_posts(10)
        response = Response(posts)
        response["Cache-Control"] = f"public, max-age={PUBLIC_CACHE_SECONDS}"
        return response
