from typing import Any
from storage_redis import StorageRedis


PREFIX = 'user_storage'


class UserStorage:
    """
    Stores miscellaneous user data
    """
    @classmethod
    async def create(cls, prefix):
        self = UserStorage()
        composite_prefix = f'{PREFIX}:{prefix}:'
        self._redis = await StorageRedis.create(composite_prefix)
        return self

    def __init__(self):
        self._redis: StorageRedis

    async def get(self, user_id: int, key: str) -> Any:
        composite_key = f'{str(user_id)}:{key}'
        return await self._redis.get_value(composite_key)

    async def set(self, user_id: int, key: str, value: Any):
        composite_key = f'{str(user_id)}:{key}'
        return await self._redis.set_value(composite_key, value)

    async def get_full_set(self, user_id: int, key: str) -> Any:
        composite_key = f'{str(user_id)}:{key}'
        return await self._redis.get_set(composite_key)

    async def add_set_member(self,
                             user_id: int,
                             key: str,
                             value: Any,
                             *values):
        composite_key = f'{str(user_id)}:{key}'
        return await self._redis.add_set_member(composite_key, value, *values)

    async def delete(self, user_id: int, key: str):
        composite_key = f'{str(user_id)}:{key}'
        return await self._redis.delete(composite_key)

    async def delete_by_pattern(self, user_id: int, pattern: str):
        composite_pattern = f'{str(user_id)}:{pattern}'
        await self._redis.delete_by_pattern(composite_pattern)
