from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.dispatcher import Dispatcher, FSMContext
from typing import Optional
from datetime_parser import get_today


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
            count = data.get('appeals_sent_count', None)

            if count is None:
                data['appeals_sent_count'] = 0
                return 0

            return count

    async def get_appeals_today_count(self) -> int:
        async with self._dp.current_state(chat=self._bot_id,
                                          user=self._bot_id).proxy() as data:
            self._update_today_count(data, 0)
            return data.get('appeals_sent_today_count', None)

    async def get_appeals_yesterday_count(self) -> int:
        async with self._dp.current_state(chat=self._bot_id,
                                          user=self._bot_id).proxy() as data:
            self._update_today_count(data, 0)
            return data.get('appeals_sent_yesterday_count', None)

    async def update_appeals_count(self, amount=1):
        async with self._dp.current_state(chat=self._bot_id,
                                          user=self._bot_id).proxy() as data:
            self._update_whole_count(data, amount)
            self._update_today_count(data, amount)

    def _update_whole_count(self, data: FSMContextProxy, amount: int):
        count = data.get('appeals_sent_count', None)

        if count is None:
            data['appeals_sent_count'] = amount
        else:
            data['appeals_sent_count'] += amount

    def _update_today_count(self, data: FSMContextProxy, amount: int):
        count = data.get('appeals_sent_today_count', None)
        date = data.get('appeals_sent_today_date', None)
        today = get_today()

        if count is None or date is None:
            self._save_yesterday(data, 0)
            data['appeals_sent_today_count'] = amount
            data['appeals_sent_today_date'] = today
            return

        if today != date:
            self._save_yesterday(data, count)
            data['appeals_sent_today_count'] = amount
            data['appeals_sent_today_date'] = today
            return

        data['appeals_sent_today_count'] += amount

    def _save_yesterday(self, data: FSMContextProxy, amount: int):
        data['appeals_sent_yesterday_count'] = amount

    def set_bot_id(self, bot_id: int):
        self._bot_id = bot_id
