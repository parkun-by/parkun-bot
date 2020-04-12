from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.dispatcher import Dispatcher, FSMContext
from typing import Optional


class BotStorage():
    def __init__(self, dispatcher: Dispatcher):
        self._dp = dispatcher
        self._bot_id: Optional[int] = None

    async def get_bans(self) -> dict:
        async with self._dp.current_state(chat=self._bot_id,
                                          user=self._bot_id).proxy() as data:
            return data.get('banned_users', dict())

    async def set_bans(self, bans: dict):
        async with self._dp.current_state(chat=self._bot_id,
                                          user=self._bot_id).proxy() as data:
            data['banned_users'] = bans

    async def get_appeals_count(self) -> int:
        async with self._dp.current_state(chat=self._bot_id,
                                          user=self._bot_id).proxy() as data:
            count = data.get('appeals_sent', None)

            if count is None:
                data['appeals_sent'] = 0
                return 0

            return count

    async def count_sent_appeal(self, amount=1):
        async with self._dp.current_state(chat=self._bot_id,
                                          user=self._bot_id).proxy() as data:
            count = data.get('appeals_sent', None)

            if count is None:
                data['appeals_sent'] = amount
            else:
                data['appeals_sent'] += amount

    def set_bot_id(self, bot_id: int):
        self._bot_id = bot_id
