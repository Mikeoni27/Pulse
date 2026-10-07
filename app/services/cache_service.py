import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Lazy singleton Redis client."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def cache_get(key: str) -> dict[str, Any] | None:
    r = get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Corrupt entry — treat as miss
        await r.delete(key)
        return None


async def cache_set(key: str, value: dict[str, Any], ttl_seconds: int = 300) -> None:
    r = get_redis()
    await r.set(key, json.dumps(value), ex=ttl_seconds)


async def cache_delete(key: str) -> None:
    r = get_redis()
    await r.delete(key)


def link_cache_key(short_code: str) -> str:
    return f"link:{short_code}"