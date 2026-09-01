from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework_api_key.permissions import BaseHasAPIKey

from apikeys.models import ClientAPIKey


class HasClientAPIKey(BaseHasAPIKey):
    model = ClientAPIKey


IsAuthenticatedOrHasAPIKey: type[BasePermission] = IsAuthenticated | HasClientAPIKey
