from __future__ import annotations

import time

from django.core.cache import cache

_CACHE_KEY = "vmp_circuit_breaker_open_until"
_DEFAULT_COOLDOWN = 7200


def open(seconds: int = _DEFAULT_COOLDOWN) -> None:
    open_until = time.time() + seconds
    cache.set(_CACHE_KEY, open_until, timeout=seconds)


def close() -> None:
    cache.delete(_CACHE_KEY)


def seconds_remaining() -> int:
    open_until = cache.get(_CACHE_KEY)
    if open_until is None:
        return 0
    remaining = int(open_until - time.time())
    if remaining <= 0:
        return 0
    return remaining


def is_open() -> bool:
    return seconds_remaining() > 0
