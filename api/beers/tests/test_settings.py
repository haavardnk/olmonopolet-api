from __future__ import annotations

import importlib

import pytest

import config.settings as project_settings


def test_no_redis_env_uses_local_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as context:
        context.delenv("REDIS_URL", raising=False)
        context.delenv("REDIS_CACHE_URL", raising=False)
        context.delenv("REDIS_Q_URL", raising=False)
        settings_module = importlib.reload(project_settings)

        cache_settings = settings_module.CACHES["default"]
        assert (
            cache_settings["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"
        )
        assert cache_settings["LOCATION"] == "beerapi-local"
        assert settings_module.Q_CLUSTER["orm"] == "default"
        assert "redis" not in settings_module.Q_CLUSTER

    importlib.reload(project_settings)


def test_redis_env_uses_redis_cache_and_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_url = "redis://:secret@redis:6379/0"
    queue_url = "redis://:secret@redis:6379/1"
    fallback_url = "redis://:secret@redis:6379/9"

    with monkeypatch.context() as context:
        context.setenv("REDIS_URL", fallback_url)
        context.setenv("REDIS_CACHE_URL", cache_url)
        context.setenv("REDIS_Q_URL", queue_url)
        settings_module = importlib.reload(project_settings)

        cache_settings = settings_module.CACHES["default"]
        assert (
            cache_settings["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
        )
        assert cache_settings["LOCATION"] == cache_url
        assert cache_settings["KEY_PREFIX"] == "beerapi"
        assert cache_settings["TIMEOUT"] == 60 * 15
        assert settings_module.Q_CLUSTER["redis"] == queue_url
        assert "orm" not in settings_module.Q_CLUSTER

    importlib.reload(project_settings)
