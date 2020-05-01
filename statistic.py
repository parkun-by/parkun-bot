from datetime import datetime, timedelta
from typing import Optional
import json

import aiohttp

from bot_storage import BotStorage
import config
import users

VERIFIED = 'verified_users'
TOTAL = 'total_users'


class Statistic():
    def __init__(self, bot_storage: BotStorage):
        self._storage = dict()
        self._bot_storage = bot_storage

    async def get_appeal_queue_size(self) -> int:
        url = f'http://{config.RABBIT_LOGIN}:{config.RABBIT_PASSWORD}@' + \
            f'{config.RABBIT_HOST}:{config.RABBIT_HTTP_PORT}/' + \
            f'api/queues/%2F/{config.RABBIT_QUEUE_APPEALS}'

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url) as response:
                if response.status != 200:
                    return 777

                queue_data = await response.json()
                messages_count: int = queue_data.get('messages', 888)
                return messages_count

    async def get_appeals_sent_count(self) -> int:
        return await self._bot_storage.get_appeals_count()

    async def get_appeals_sent_today_count(self) -> int:
        return await self._bot_storage.get_appeals_today_count()

    async def get_appeals_sent_yesterday_count(self) -> int:
        return await self._bot_storage.get_appeals_yesterday_count()

    async def get_total_users_count(self) -> int:
        return await self._get_cached_users_count(TOTAL) or \
            await self._count_users(TOTAL)

    async def get_registered_users_count(self) -> int:
        return await self._get_cached_users_count(VERIFIED) or \
            await self._count_users(VERIFIED)

    async def _get_cached_users_count(self, users_type: str) -> Optional[int]:
        EXPIRATION_TIME = timedelta(hours=1)
        current_time = datetime.now()

        users_count: Optional[int] = self._storage.get(users_type, None)

        if not users_count:
            return None

        timestamp = self._storage.get(f'{users_type}_timestamp', current_time)

        if current_time - timestamp < EXPIRATION_TIME:
            return users_count
        else:
            return None

    async def _count_users(self, users_type: str) -> int:
        total_users_count = 0
        registered_users_count = 0

        async for user_data in users.every(id_only=False):
            total_users_count += 1
            user_verified = user_data.get('verified', False)

            if user_verified:
                registered_users_count += 1

        self._storage[VERIFIED] = registered_users_count
        self._storage[f'{VERIFIED}_timestamp'] = datetime.now()
        self._storage[TOTAL] = total_users_count
        self._storage[f'{TOTAL}_timestamp'] = datetime.now()

        if users_type == VERIFIED:
            return registered_users_count
        else:
            return total_users_count

    async def count_sent_appeal(self, amount=1):
        await self._bot_storage.update_appeals_count(amount)
