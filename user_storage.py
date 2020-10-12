from storage_redis import StorageRedis


PREFIX = 'user_storage:'


class UserStorage:
    """
    Stores miscellaneous user data
    """
    @classmethod
    async def create(cls):
        self = UserStorage()
        self._redis = await StorageRedis.create(PREFIX)
        return self

    def __init__(self):
        self._redis: StorageRedis

    async def get_photos_paths(self, user_id: int, appeal_id: int):
        """
        Returns user's violation photos on-disk paths
        """
        key = f'{str(user_id)}:{str(appeal_id)}:photos_paths'
        return await self._redis.get_value(key)

    async def set_photos_paths(self,
                               user_id: int,
                               appeal_id: int,
                               paths: list):
        """
        Saves user's violation photos on-disk paths
        """
        key = f'{str(user_id)}:{str(appeal_id)}:photos_paths'
        return await self._redis.set_value(key, paths)
