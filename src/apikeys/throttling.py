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
            api_key = ClientAPIKey.objects.get_from_key(raw_key)
        except ClientAPIKey.DoesNotExist:
            return True

        rate = self.THROTTLE_RATES.get(f"apikey_{api_key.tier}")
        if rate is None:
            return True

        self.rate = rate
        self.num_requests, self.duration = self.parse_rate(rate)
        self.key = f"throttle_apikey_{api_key.prefix}"
        self.history = self.cache.get(self.key, [])
        self.now = self.timer()
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()

    def get_cache_key(self, request, view) -> None:
        return None
