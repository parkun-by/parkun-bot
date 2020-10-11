import logging
from asyncio import Semaphore
from contextlib import asynccontextmanager
from typing import Any, Dict

from datetime_parser import get_today
from storage_redis import StorageRedis

PREFIX = "bot_storage:"
semaphore = Semaphore()
logger = logging.getLogger(__name__)


class BotStorage():
    @classmethod
    async def create(cls):
        self = BotStorage()
        self._redis = await StorageRedis.create(PREFIX)
        return self

    def __init__(self):
        self._redis: StorageRedis

    async def get_bans(self) -> Dict[str, Any]:
        return await self._redis.get_value('banned_users')

    async def set_bans(self, bans: dict):
        await self._redis.set_value('banned_users', bans)

    async def get_appeals_count(self) -> int:
        count = await self._redis.get_value('appeals_sent_count', 0)
        return int(count)

    async def get_appeals_today_count(self) -> int:
        return await self._redis.get_value('appeals_sent_today_count', 0)

    async def get_appeals_yesterday_count(self) -> int:
        return await self._redis.get_value('appeals_sent_yesterday_count', 0)

    async def update_appeals_count(self, amount=1):
        await self._update_whole_count(amount)
        await self._update_today_count(amount)

    async def _update_whole_count(self, amount: int):
        count = await self._redis.get_value('appeals_sent_count', 0)
        await self._redis.set_value('appeals_sent_count', int(count) + amount)

    async def _update_today_count(self, amount: int):
        count = await self._redis.get_value('appeals_sent_today_count', None)
        date = await self._redis.get_value('appeals_sent_today_date', None)
        today = get_today()

        if count is None or date is None:
            await self._save_yesterday(0)
            await self._redis.set_value('appeals_sent_today_count', amount)
            await self._redis.set_value('appeals_sent_today_date', today)
            return

        if today != date:
            await self._save_yesterday(count)
            await self._redis.set_value('appeals_sent_today_count', amount)
            await self._redis.set_value('appeals_sent_today_date', today)
            return

        await self._redis.set_value('appeals_sent_today_count',
                                    int(count) + amount)

    async def _save_yesterday(self, amount: int):
        await self._redis.set_value('appeals_sent_yesterday_count', amount)

    @asynccontextmanager
    async def tasks(self):
        async with semaphore:
            tasks = await self.get_scheduled_tasks()

            try:
                yield tasks
            finally:
                await self.set_scheduled_tasks(tasks)

    async def get_scheduled_tasks(self) -> Dict[str, list]:
        return await self._redis.get_value('scheduled_tasks')

    async def set_scheduled_tasks(self, tasks: Dict[str, list]):
        await self._redis.set_value('scheduled_tasks', tasks)
