import asyncio
import logging
from asyncio import AbstractEventLoop
from typing import Callable, Dict

import datetime_parser
from bot_storage import BotStorage

logger = logging.getLogger(__name__)


class Scheduler():
    def __init__(self, bot_storage: BotStorage,
                 executors: Dict[str, Callable],
                 loop: AbstractEventLoop):
        self.storage = bot_storage
        self.executors = executors
        self.loop = loop

    async def start(self):
        logger.info('Запуск шедулера')

        while True:
            tasks = await self.storage.get_scheduled_tasks()
            current_time_str = datetime_parser.get_current_datetime_str()
            current_time = datetime_parser.get_current_datetime()

            for user_id in tasks:
                task = tasks[user_id]
                execute_time = task.get('execute_time', current_time_str)

                execute_time = \
                    datetime_parser.datetime_from_string(execute_time)

                if current_time >= execute_time:
                    executor = self.executors[task['executor']]
                    kvargs = task['kvargs']

                    asyncio.run_coroutine_threadsafe(executor(**kvargs),
                                                     self.loop)

                    await self.storage.delete_scheduled_task(user_id)

            await asyncio.sleep(60)
