from datetime import datetime, timedelta
import json

import aiohttp
import aioredis

from bot_storage import BotStorage
import config


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
        redis = await aioredis.create_redis(
            f'redis://{config.REDIS_HOST}:{config.REDIS_PORT}',
            password=config.REDIS_PASSWORD)

        keys = []
        cur = b'0'  # set initial cursor to 0
        verified_users = 0

        while cur:
            cur, keys = await redis.scan(cur, match='fsm:*:*:data')

            for key in keys:
                val = await redis.get(key)
                user_data: dict = json.loads(val)
                user_verified = user_data.get('verified', False)

                if user_verified:
                    verified_users += 1

        redis.close()
        self._storage['verified_users'] = verified_users
        self._storage['verified_users_timestamp'] = datetime.now()
        return verified_users
