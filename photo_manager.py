import asyncio
import logging
import os
import secrets
import shutil
import time
from asyncio.events import AbstractEventLoop
from contextlib import contextmanager
from typing import Any, Awaitable, List, Optional, Union

import aiohttp
import pyimgbox
from aiogram import Bot
from aiogram.types.photo_size import PhotoSize

import config
from numberplates import recognize_numberplates
from telegraph import Telegraph
from user_storage import UserStorage

logger = logging.getLogger(__name__)
CURRENT = "current"
STORAGE_PREFIX = "photo_manager"


class PhotoManager:
    def __init__(self, loop: AbstractEventLoop, bot: Bot):
        self.files_dir = config.TEMP_FILES_PATH
        self.task_storage = dict()
        self.data_storage: UserStorage
        self.telegraph = Telegraph(loop)
        self._bot = bot

        try:
            os.makedirs(self.files_dir)
        except FileExistsError:
            pass

    @classmethod
    async def create(cls, loop: AbstractEventLoop, bot: Bot):
        self = PhotoManager(loop, bot)
        self.data_storage = await UserStorage.create(STORAGE_PREFIX)
        return self

    def __del__(self):
        shutil.rmtree(self.files_dir, ignore_errors=True)

    def valid(self, photos_data: dict) -> bool:
        try:
            assert(photos_data['file_paths'])
            assert(photos_data['urls'])
            assert(photos_data['page_url'])

            assert (len(photos_data['file_paths']) == len(photos_data['urls']))

            return True
        except Exception:
            return False

    def stash_photo(self, user_id: int, photo_tg_object: PhotoSize):
        tasks: list

        with self.tasks(self.task_storage,
                        list(),
                        user_id,
                        CURRENT,
                        'store_photo_tasks') as tasks:
            storing_task = asyncio.create_task(
                self.store_photo(user_id, photo_tg_object)
            )

            tasks.append(storing_task)

        with self.tasks(self.task_storage,
                        list(),
                        user_id,
                        CURRENT,
                        'numberplate_tasks') as tasks:
            numberplate_task = asyncio.create_task(
                self.recognize_numberplate(user_id, storing_task)
            )

            tasks.append(numberplate_task)

        with self.tasks(self.task_storage,
                        list(),
                        user_id,
                        CURRENT,
                        'upload_to_cloud_tasks') as tasks:
            upload_to_cloud_task = asyncio.create_task(
                self.upload_to_cloud(user_id, storing_task)
            )

            tasks.append(upload_to_cloud_task)

    async def store_photo(self,
                          user_id: int,
                          photo_tg_object: PhotoSize,
                          stash_id: Union[int, str] = CURRENT) -> str:
        folder_path = self._get_user_dir(user_id, stash_id)
        photo_file = await self._bot.get_file(photo_tg_object['file_id'])
        file_name = photo_file.file_path.split('/')[-1]
        file_path = self.get_unique_file_path(folder_path, file_name)
        await photo_tg_object.download(file_path)

        await self.data_storage.add_set_member(user_id,
                                               key=f'{stash_id}:file_paths',
                                               value=file_path)
        return file_path

    async def upload_to_cloud(self,
                              user_id: int,
                              photo_file_path: Awaitable,
                              stash_id: Union[int, str] = CURRENT) -> str:
        file_path = await photo_file_path
        permanent_url = await self._upload_photo(file_path)

        await self.data_storage.add_set_member(user_id,
                                               key=f'{stash_id}:urls',
                                               value=permanent_url)
        return permanent_url

    async def recognize_numberplate(
            self,
            user_id: int,
            photo_file_path: Awaitable,
            stash_id: Union[int, str] = CURRENT) -> List[str]:
        file_path = await photo_file_path

        if recognized_numbers := await recognize_numberplates(file_path):
            await self.data_storage.add_set_member(user_id,
                                                   f'{stash_id}:numberplates',
                                                   *recognized_numbers)

        return recognized_numbers

    def get_unique_file_path(self, folder_path: str, file_name: str) -> str:
        timestamp = str(time.time()).replace('.', '')
        file_path = os.path.join(folder_path, timestamp + file_name)
        return file_path

    def stash_page(self, user_id: int, title: str):
        page_tasks: list

        with self.tasks(self.task_storage,
                        list(),
                        user_id, CURRENT, 'page_tasks') as page_tasks:
            storing_task = asyncio.create_task(
                self._create_page(user_id, title)
            )

            page_tasks.append(storing_task)

    async def _create_page(self, user_id: int, title: str):
        await self._wait_for_done(user_id, CURRENT, 'store_photo_tasks')
        await self._wait_for_done(user_id, CURRENT, 'upload_to_cloud_tasks')

        urls: list = await self.data_storage.get_full_set(
            user_id,
            key=f'{CURRENT}:urls')

        page_url = await self.telegraph.create_page(urls, title)

        await self.data_storage.set(user_id,
                                    key=f'{CURRENT}:page_url',
                                    value=page_url)

    async def set_id_to_current_photos(self, user_id: int, appeal_id: int):
        await self.clear_storage(user_id, appeal_id)
        await self._wait_for_done(user_id, CURRENT, 'store_photo_tasks')
        await self._wait_for_done(user_id, CURRENT, 'numberplate_tasks')
        await self._wait_for_done(user_id, CURRENT, 'upload_to_cloud_tasks')
        await self._wait_for_done(user_id, CURRENT, 'page_tasks')

        # rename folder_name in file paths
        old_paths: list = await self.data_storage.get_full_set(
            user_id,
            key=f'{CURRENT}:file_paths')

        file_paths = list(map(
            lambda path: path.replace(CURRENT, str(appeal_id)),
            old_paths
        ))

        await self.data_storage.add_set_member(
            user_id,
            f'{appeal_id}:file_paths',
            *file_paths)

        # rename folder_name in numberplates
        old_numberplates_path: list = await self.data_storage.get_full_set(
            user_id,
            key=f'{CURRENT}:numberplates')

        numberplates = list(map(
            lambda path: path.replace(CURRENT, str(appeal_id)),
            old_numberplates_path
        ))

        await self.data_storage.add_set_member(
            user_id,
            f'{appeal_id}:numberplates',
            *numberplates)

        # rename folder_name in urls
        old_urls: list = await self.data_storage.get_full_set(
            user_id,
            key=f'{CURRENT}:urls')

        new_urls = list(map(
            lambda path: path.replace(CURRENT, str(appeal_id)),
            old_urls
        ))

        await self.data_storage.add_set_member(
            user_id,
            f'{appeal_id}:urls',
            *new_urls)

        # rename folder name in page_url
        page_url: str = await self.data_storage.get(user_id,
                                                    f'{CURRENT}:page_url')

        await self.data_storage.set(user_id,
                                    key=f'{appeal_id}:page_url',
                                    value=page_url)

        # rename key in task storage
        with self.tasks(self.task_storage, dict(), user_id) as user_stash:
            appeal_stash: dict = user_stash.get(CURRENT, {})
            user_stash[appeal_id] = appeal_stash
            user_stash.pop(CURRENT, None)

        # rename files folder
        current_path = self._get_user_dir(user_id, CURRENT)
        new_path = self._get_user_dir_name(user_id, appeal_id)
        os.rename(current_path, new_path)

    async def get_photo_data(self, user_id: int, appeal_id: int) -> dict:
        await self._wait_for_done(user_id, appeal_id, 'store_photo_tasks')
        await self._wait_for_done(user_id, appeal_id, 'upload_to_cloud_tasks')
        await self._wait_for_done(user_id, appeal_id, 'page_tasks')

        appeal_stash = dict()

        appeal_stash['urls'] = await self.data_storage.get_full_set(
            user_id,
            f'{appeal_id}:urls')

        appeal_stash['file_paths'] = await self.data_storage.get_full_set(
            user_id,
            f'{appeal_id}:file_paths')

        appeal_stash['page_url'] = await self.data_storage.get(
            user_id,
            f'{appeal_id}:page_url')

        return appeal_stash

    async def numberplate_tasks_in_progress(
            self,
            user_id: int,
            appeal_id: Union[int, str] = CURRENT) -> bool:
        with self.tasks(self.task_storage,
                        list(),
                        user_id,
                        appeal_id,
                        'numberplate_tasks') as tasks:
            for task in tasks:
                if not task.done():
                    return True

        return False

    async def cancel_recognition_task(
            self,
            user_id: int,
            appeal_id: Union[int, str] = CURRENT):
        with self.tasks(self.task_storage,
                        list(),
                        user_id,
                        appeal_id,
                        'numberplate_tasks') as tasks:
            for task in tasks:
                if not task.done():
                    task.cancel()

    async def get_numberplates(
            self,
            user_id: int,
            appeal_id: Union[int, str] = CURRENT) -> List[str]:
        await self._wait_for_done(user_id, appeal_id, 'numberplate_tasks')

        numberplates = await self.data_storage.get_full_set(
            user_id, f'{appeal_id}:numberplates')

        return numberplates

    async def _wait_for_done(self,
                             user_id: int,
                             appeal_id: Union[int, str],
                             tasks_group_name: str):
        with self.tasks(self.task_storage,
                        list(),
                        user_id, appeal_id, tasks_group_name) as tasks:
            for task in tasks:
                if not task.done():
                    await task

            tasks = []

    async def _cancel_tasks(self,
                            user_id: int,
                            appeal_id: Union[int, str],
                            tasks_group_name: str):
        with self.tasks(self.task_storage,
                        list(),
                        user_id, appeal_id, tasks_group_name) as tasks:
            for task in tasks:
                if not task.cancelled():
                    task.cancel()

            tasks = []

    def _get_user_dir_name(self,
                           user_id: int,
                           appeal_id: Union[int, str]) -> str:
        return os.path.join(self.files_dir, str(user_id), str(appeal_id))

    def _get_user_dir(self, user_id: int, appeal_id: Union[int, str]) -> str:
        dir_path = self._get_user_dir_name(user_id, appeal_id)

        try:
            os.makedirs(dir_path)
            return dir_path
        except FileExistsError:
            return dir_path

    async def clear_storage(self,
                            user_id: int,
                            appeal_id: Union[int, str] = CURRENT,
                            with_files=True) -> None:
        await self._clear_task_storage(user_id, appeal_id)
        await self._clear_data_storage(user_id, appeal_id)

        if with_files:
            shutil.rmtree(self._get_user_dir(user_id, appeal_id),
                          ignore_errors=True)

    async def _clear_task_storage(self,
                                  user_id: int,
                                  appeal_id: Union[int, str]):
        await self._wait_for_done(user_id, appeal_id, 'store_photo_tasks')
        await self._wait_for_done(user_id, appeal_id, 'page_tasks')
        await self._wait_for_done(user_id, appeal_id, 'numberplate_tasks')
        await self._wait_for_done(user_id, appeal_id, 'upload_to_cloud_tasks')

        user_stash: dict = self.task_storage.get(user_id, {})
        user_stash.pop(appeal_id, None)

        if not user_stash:
            self.task_storage.pop(user_id, None)

    async def _clear_data_storage(self,
                                  user_id: int,
                                  appeal_id: Union[int, str]):
        await self.data_storage.delete_by_pattern(
            user_id,
            pattern=f'{str(appeal_id)}:*')

    async def _upload_photo(self, file_path: str) -> str:
        return await self._upload_photo_to_telegraph(file_path) or \
            await self._upload_photo_to_imgbox(file_path)

    async def _upload_photo_to_imgbox(self, file_path: str) -> str:
        async with pyimgbox.Gallery(title="parkun_by_bot") as gallery:
            submission = await gallery.upload(file_path)

        if submission.get("success", False):
            return submission.get("image_url", "")
        else:
            return ""

    async def _upload_photo_to_telegraph(self, file_path: str) -> str:
        uploaded = False
        tries = 5
        file_id = ''

        while not uploaded:
            form = aiohttp.FormData(quote_fields=False)

            with open(file_path, 'rb') as file:
                form.add_field(secrets.token_urlsafe(8),
                               file,
                               filename='file',
                               content_type='image/jpg')

                upload_url = 'https://telegra.ph/upload'

                try:
                    async with aiohttp.ClientSession() as http_session:
                        async with http_session.post(upload_url,
                                                     data=form) as r:
                            result = await r.json()
                except Exception:
                    logger.exception("Error while upload photo to telegraph")
                    result = None

            if (not result) \
                    or (isinstance(result, dict) and 'error' in result):
                if tries != 0:
                    await asyncio.sleep(1)
                    tries -= 1
                else:
                    uploaded = True
            else:
                uploaded = True
                result: Optional[dict] = result[0]
                file_id = result.get("src", "")

        if file_id:
            return 'https://telegra.ph' + file_id
        else:
            return ""

    @contextmanager
    def tasks(self, storage: dict, default: Any, path: str, *paths) -> Any:
        tasks = self.get_tasks(storage, default, path, *paths)

        try:
            yield tasks
        finally:
            self.set_tasks(storage, tasks, path, *paths)

    def set_tasks(self, storage: dict, value: Any, path: str, *paths):
        """
        save value by path
        """
        if paths:
            storage.setdefault(path, dict())
            self.set_tasks(storage[path], value, *paths)
        else:
            storage[path] = value

    def get_tasks(self, storage: dict, default: Any, path: str, *paths):
        """
        recursive extracting value from dict tree
        """
        tasks = storage.get(path, dict())

        if paths:
            tasks = self.get_tasks(tasks, default, *paths)
        elif not tasks:
            tasks = default

        return tasks
