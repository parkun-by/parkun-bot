import asyncio
from datetime import datetime, timedelta
from typing import Awaitable


class Timer:
    def __init__(self, stop_callback, loop):
        self.tasks_to_stop = {}
        self.stop_callback = stop_callback
        self.loop = loop

    async def start(self):
        while True:
            await self._check_for_overdue()
            await asyncio.sleep(60)

    async def _check_for_overdue(self):
        delete_list = []

        for task in self.tasks_to_stop:
            if datetime.utcnow() >= self.tasks_to_stop[task]['stop_time']:
                asyncio.run_coroutine_threadsafe(
                    self.stop_callback(
                        self.tasks_to_stop[task]['description']),
                    self.loop)

                delete_list.append(task)

        for task in delete_list:
            self.tasks_to_stop.pop(task, '')

    def add_task(self, task_description: dict, timer_min: float) -> None:
        user_id = str(task_description["user_id"])
        appeal_id = str(task_description["appeal_id"])
        key = f'{user_id}_{appeal_id}'

        self.tasks_to_stop[key] = {
            'description': task_description,
            'stop_time': datetime.utcnow() + timedelta(minutes=timer_min)
        }

    def delete_task(self, user_id: int, appeal_id: int) -> None:
        key = f'{str(user_id)}_{str(appeal_id)}'
        self.tasks_to_stop.pop(key, '')
