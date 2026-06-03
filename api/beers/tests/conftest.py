import pytest
import requests
from curl_cffi import requests as cffi


@pytest.fixture(autouse=True)
def route_curl_cffi_through_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(self: cffi.Session, url: str, *args: object, **kwargs: object) -> requests.Response:
        return requests.get(url)

    monkeypatch.setattr(cffi.Session, "get", fake_get)
