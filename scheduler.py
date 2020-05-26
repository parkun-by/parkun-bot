import asyncio
import logging
from asyncio import AbstractEventLoop
from typing import Callable, Dict

import datetime_parser
from bot_storage import BotStorage

logger = logging.getLogger(__name__)

RELOAD_BOUNDARY = 'reload_boundary'
CANCEL_ON_IDLE = 'cancel_on_idle'

ONE_PER_USER = 'one_per_user'

task_types = {
    RELOAD_BOUNDARY: {
        ONE_PER_USER: False,
    },

    CANCEL_ON_IDLE: {
        ONE_PER_USER: True,
    }
}


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

            for user_id in tasks:
                user_tasks = tasks[user_id]
                user_tasks = await self.handle_tasks(user_tasks)
                tasks[user_id] = user_tasks

            await self.storage.set_scheduled_tasks(tasks)
            await asyncio.sleep(60)

    async def handle_tasks(self, user_tasks: list) -> list:
        current_time_str = datetime_parser.get_current_datetime_str()
        current_time = datetime_parser.get_current_datetime()

        for task_num, task in enumerate(user_tasks):
            execute_time = task.get('execute_time', current_time_str)
            execute_time = datetime_parser.datetime_from_string(execute_time)

            if current_time >= execute_time:
                executor = self.executors[task['executor']]
                kvargs = task['kvargs']

                try:
                    await executor(**kvargs)
                except Exception:
                    logger.exception('Задание упало')

                user_tasks.pop(task_num)

        return user_tasks

    async def add_task(self, task: dict):
        tasks = await self.storage.get_scheduled_tasks()
        user_id = task['user_id']
        user_tasks: list = tasks[user_id]
        task_type: str = task['executor']

        logger.info(f'Добавляем задание в шедулер: {task_type} - {user_id}')

        if task_types[task_type][ONE_PER_USER]:
            for task_num, user_task in enumerate(user_tasks):
                if user_task['executor'] == task_type:
                    user_tasks.pop(task_num)

        user_tasks.append(task)
        tasks[task['user_id']] = user_tasks
        await self.storage.set_scheduled_tasks(tasks)

    def add_executor(self, task_type: str, executor: Callable):
        self.executors[task_type] = executor
