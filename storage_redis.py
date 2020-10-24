import json
import logging
from typing import Any, Callable

import aioredis

import config

logger = logging.getLogger(__name__)


def safe_redis(func: Callable) -> Callable:
    async def try_function(*args, default=None):
        try:
            return await func(*args)
        except aioredis.errors.ReplyError:
            logger.error("Redis еще не готов")
        except Exception:
            logger.exception("Что-то не так с хранилищем")

        return default

    return try_function


class StorageRedis:
    """
    Functions to safe read/write to redis
    """
    @classmethod
    async def create(cls, prefix: str):
        self = StorageRedis(prefix)

        self._redis = await aioredis.create_redis(
            f'redis://{config.REDIS_HOST}:{config.REDIS_PORT}',
            password=config.REDIS_PASSWORD)

        return self

    def __init__(self, prefix: str):
        self.PREFIX = prefix
        self._redis: aioredis = None

    @safe_redis
    async def get_value(self, key: str, default: Any = dict()) -> Any:
        key = self.PREFIX + key

        if await self._redis.exists(key):
            raw_value = await self._redis.get(key)
            value: dict = json.loads(raw_value)
            return value or default
        else:
            return default

    @safe_redis
    async def set_value(self, key: str, value: Any):
        key = self.PREFIX + key
        raw_value = json.dumps(value)
        await self._redis.set(key, raw_value)

    @safe_redis
    async def add_set_member(self, key: str, value: Any, *values):
        key = self.PREFIX + key
        values = (value, *values)
        await self._redis.sadd(key, *values)

    @safe_redis
    async def get_set(self, key: str, default: Any = ()) -> Any:
        key = self.PREFIX + key

        if await self._redis.exists(key):
            raw_values = await self._redis.smembers(key)

            value = list(map(lambda raw_value: raw_value.decode('utf8'),
                             raw_values))

            return value or default
        else:
            return default

    @safe_redis
    async def delete(self, key: str, *keys):
        keys = (*keys, key)
        keys = map(lambda key: self.PREFIX + key, keys)
        await self._redis.delete(*keys)

    @safe_redis
    async def keys(self, pattern: str):
        pattern = self.PREFIX + pattern
        return await self._redis.keys(pattern)

    @safe_redis
    async def delete_by_pattern(self, pattern: str):
        keys = await self.keys(pattern)

        if keys:
            await self._redis.delete(*keys)
