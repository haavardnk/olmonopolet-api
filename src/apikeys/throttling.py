from typing import cast

from rest_framework.throttling import SimpleRateThrottle
from rest_framework_api_key.permissions import KeyParser

from apikeys.models import ClientAPIKey


class TieredAPIKeyThrottle(SimpleRateThrottle):
    key_parser = KeyParser()

    def __init__(self) -> None:
        pass

    def allow_request(self, request, view) -> bool:
        raw_key = self.key_parser.get(request)
        if not raw_key:
            return True
        try:
            api_key = cast(ClientAPIKey, ClientAPIKey.objects.get_from_key(raw_key))
        except ClientAPIKey.DoesNotExist:
            return True

        rate = self.THROTTLE_RATES.get(f"apikey_{api_key.tier}")
        if rate is None:
            return True

        self.rate = rate
        num_requests, duration = self.parse_rate(rate)
        if num_requests is None or duration is None:
            return True

        self.num_requests = num_requests
        self.duration = duration
        self.key = f"throttle_apikey_{api_key.prefix}"
        self.history = self.cache.get(self.key, [])
        self.now = self.timer()
        while self.history and self.history[-1] <= self.now - duration:
            self.history.pop()
        if len(self.history) >= num_requests:
            return self.throttle_failure()
        return self.throttle_success()

    def get_cache_key(self, request, view) -> None:
        return None
