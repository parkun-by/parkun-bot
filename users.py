from typing import Iterator, Union
import aioredis
import config
import json


async def verified():
    redis = await aioredis.create_redis(
        f'redis://{config.REDIS_HOST}:{config.REDIS_PORT}',
        password=config.REDIS_PASSWORD)

    keys = []
    cur = b'0'  # set initial cursor to 0

    while cur:
        cur, keys = await redis.scan(cur, match='fsm:*:*:data')

        for key in keys:
            val = await redis.get(key)
            user_data: dict = json.loads(val)
            user_verified = user_data.get('verified', False)

            if user_verified:
                yield user_data

    redis.close()


async def every_id() -> Iterator[int]:
    redis = await aioredis.create_redis(
        f'redis://{config.REDIS_HOST}:{config.REDIS_PORT}',
        password=config.REDIS_PASSWORD)

    keys = []
    cur = b'0'  # set initial cursor to 0

    while cur:
        cur, keys = await redis.scan(cur, match='fsm:*:*:data')

        for key in keys:
            id_data = str(key).split(':')
            # chat_id = id_data[1]
            user_id = id_data[2]
            yield int(user_id)

    redis.close()


async def every() -> Iterator[dict]:
    redis = await aioredis.create_redis(
        f'redis://{config.REDIS_HOST}:{config.REDIS_PORT}',
        password=config.REDIS_PASSWORD)

    keys = []
    cur = b'0'  # set initial cursor to 0

    while cur:
        cur, keys = await redis.scan(cur, match='fsm:*:*:data')

        for key in keys:
            val = await redis.get(key)
            user_data: dict = json.loads(val)
            yield user_data

    redis.close()
