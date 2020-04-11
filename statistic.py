import aioredis
import aiohttp
import config
from typing import Optional

import asyncio
import json


class Statistic():
    def __init__(self):
        self._bot_id: Optional[int] = None

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
        return 10_000

    async def get_registered_users_count(self) -> int:
        redis = await aioredis.create_redis(
            f'redis://{config.REDIS_HOST}:{config.REDIS_PORT}',
            password=config.REDIS_PASSWORD)

        keys = []
        cur = b'0'  # set initial cursor to 0

        while cur:
            cur, keys = await redis.scan(cur, match='fsm:*:*:data')

        verified_users = 0

        for key in keys:
            val = await redis.get(key)
            user_data: dict = json.loads(val)
            user_verified = user_data.get('verified', False)

            if user_verified:
                verified_users += 1

        redis.close()
        return verified_users

    def set_bot_id(self, bot_id: int):
        self._bot_id = bot_id


if __name__ == "__main__":
    stats = Statistic()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(stats.get_registered_users_count())
