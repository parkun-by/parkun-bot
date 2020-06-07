import json
import logging
from asyncio import Semaphore
from contextlib import asynccontextmanager
from typing import Any, Dict, Callable

import aioredis

import config
from datetime_parser import get_today

PREFIX = "bot_storage:"
semaphore = Semaphore()
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


class BotStorage():
    def __init__(self):
        self._redis = None

    async def start(self):
        self._redis = await aioredis.create_redis(
            f'redis://{config.REDIS_HOST}:{config.REDIS_PORT}',
            password=config.REDIS_PASSWORD)

    @safe_redis
    async def _get_value(self, key: str, default: Any = dict()) -> Any:
        key = PREFIX + key

        if await self._redis.exists(key):
            raw_value = await self._redis.get(key)
            value: dict = json.loads(raw_value)
            return value or default
        else:
            return default

    @safe_redis
    async def _set_value(self, key: str, value: Any):
        key = PREFIX + key
        raw_value = json.dumps(value)
        await self._redis.set(key, raw_value)

    async def get_bans(self) -> Dict[str, Any]:
        return await self._get_value('banned_users')

    async def set_bans(self, bans: dict):
        await self._set_value('banned_users', bans)

    async def get_appeals_count(self) -> int:
        count = await self._get_value('appeals_sent_count', 0)
        return int(count)

    async def get_appeals_today_count(self) -> int:
        return await self._get_value('appeals_sent_today_count', 0)

    async def get_appeals_yesterday_count(self) -> int:
        return await self._get_value('appeals_sent_yesterday_count', 0)

    async def update_appeals_count(self, amount=1):
        await self._update_whole_count(amount)
        await self._update_today_count(amount)

    async def _update_whole_count(self, amount: int):
        count = await self._get_value('appeals_sent_count', 0)
        await self._set_value('appeals_sent_count', int(count) + amount)

    async def _update_today_count(self, amount: int):
        count = await self._get_value('appeals_sent_today_count', None)
        date = await self._get_value('appeals_sent_today_date', None)
        today = get_today()

        if count is None or date is None:
            await self._save_yesterday(0)
            await self._set_value('appeals_sent_today_count', amount)
            await self._set_value('appeals_sent_today_date', today)
            return

        if today != date:
            await self._save_yesterday(count)
            await self._set_value('appeals_sent_today_count', amount)
            await self._set_value('appeals_sent_today_date', today)
            return

        await self._set_value('appeals_sent_today_count', int(count) + amount)

    async def _save_yesterday(self, amount: int):
        await self._set_value('appeals_sent_yesterday_count', amount)

    @asynccontextmanager
    async def tasks(self):
        async with semaphore:
            tasks = await self.get_scheduled_tasks()

            try:
                yield tasks
            finally:
                await self.set_scheduled_tasks(tasks)

    async def get_scheduled_tasks(self) -> Dict[str, list]:
        return await self._get_value('scheduled_tasks')

    async def set_scheduled_tasks(self, tasks: Dict[str, list]):
        await self._set_value('scheduled_tasks', tasks)
