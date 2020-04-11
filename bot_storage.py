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

    def set_bot_id(self, bot_id: int):
        self._bot_id = bot_id
