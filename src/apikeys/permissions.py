from rest_framework.permissions import IsAuthenticated
from rest_framework_api_key.permissions import BaseHasAPIKey

from apikeys.models import ClientAPIKey


class HasClientAPIKey(BaseHasAPIKey):
    model = ClientAPIKey


IsAuthenticatedOrHasAPIKey = IsAuthenticated | HasClientAPIKey
