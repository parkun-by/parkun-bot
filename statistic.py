from datetime import datetime, timedelta
import json

import aiohttp
import aioredis

from bot_storage import BotStorage
import config
import users


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

    async def get_registered_users_count(self) -> int:
        return await self._get_cached_users_count() or \
            await self._count_users()

    async def _get_cached_users_count(self):
        EXPIRATION_TIME = timedelta(hours=1)
        current_time = datetime.now()

        verified_users = self._storage.get('verified_users', None)

        if not verified_users:
            return None

        timestamp = self._storage.get('verified_users_timestamp', current_time)

        if current_time - timestamp < EXPIRATION_TIME:
            return verified_users
        else:
            return None

    async def _count_users(self):
        verified_users = 0

        async for _ in users.verified():
            verified_users += 1

        self._storage['verified_users'] = verified_users
        self._storage['verified_users_timestamp'] = datetime.now()
        return verified_users

    async def count_sent_appeal(self, amount=1):
        await self._bot_storage.update_appeals_count(amount)
