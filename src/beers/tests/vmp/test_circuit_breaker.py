import time

import pytest
from beers.vmp import circuit_breaker
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear() -> None:
    cache.clear()


def test_starts_closed() -> None:
    assert circuit_breaker.is_open() is False
    assert circuit_breaker.seconds_remaining() == 0


def test_open_then_is_open() -> None:
    circuit_breaker.open(100)

    assert circuit_breaker.is_open() is True
    assert 0 < circuit_breaker.seconds_remaining() <= 100


def test_close() -> None:
    circuit_breaker.open(100)
    circuit_breaker.close()

    assert circuit_breaker.is_open() is False


def test_expires() -> None:
    circuit_breaker.open(1)
    time.sleep(1.1)

    assert circuit_breaker.is_open() is False
