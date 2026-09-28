"""Thin Redis cache wrapper.

Design goal: the rest of the app should never have to check "is Redis up?"
before using the cache. If Redis is unreachable or `REDIS_URL` is unset, every
method becomes a safe no-op (get returns None, set/delete do nothing) instead
of raising, so local dev and tests work without a running Redis instance.
"""

from __future__ import annotations

import json
from typing import Any

from app.utils.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover - redis is a declared dependency
    redis = None  # type: ignore[assignment]


class Cache:
    """Redis-backed cache with graceful degradation."""

    def __init__(self, redis_url: str | None) -> None:
        self._client: Any | None = None
        if redis is not None and redis_url:
            try:
                client = redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
                client.ping()
                self._client = client
            except (
                Exception
            ) as exc:  # noqa: BLE001 - deliberately broad, cache must never crash the app
                logger.warning("Redis unavailable, caching disabled: %s", exc)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def get_json(self, key: str) -> Any | None:
        if not self._client:
            return None
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache get failed for key=%s: %s", key, exc)
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        if not self._client:
            return
        try:
            self._client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache set failed for key=%s: %s", key, exc)

    def delete(self, key: str) -> None:
        if not self._client:
            return
        try:
            self._client.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache delete failed for key=%s: %s", key, exc)


_cache_instance: Cache | None = None


def get_cache() -> Cache:
    """Return a process-wide Cache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache(get_settings().redis_url)
    return _cache_instance
