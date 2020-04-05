import logging
import aiohttp
import asyncio
import os
import shutil
import secrets

from typing import Tuple, Awaitable
from telegraph import Telegraph
from asyncio.events import AbstractEventLoop


logger = logging.getLogger(__name__)


class PhotoManager:
    def __init__(self, loop: AbstractEventLoop):
        self.files_dir = os.path.join('/tmp', 'temp_files_parkun')
        self.storage = {}
        self.telegraph = Telegraph(loop)

        try:
            os.makedirs(self.files_dir)
        except FileExistsError:
            pass

    def __del__(self):
        shutil.rmtree(self.files_dir, ignore_errors=True)

    def stash_photo(self, user_id: int, appeal_id: int, temp_url: str):
        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})
        tasks: list = appeal_stash.setdefault('photo_tasks', [])

        storing_task = asyncio.create_task(
            self._store_photo(user_id, appeal_id, temp_url)
        )

        tasks.append(storing_task)
        appeal_stash['photo_tasks'] = tasks
        user_stash[appeal_id] = appeal_stash
        self.storage[user_id] = user_stash

    async def _store_photo(self, user_id: int, appeal_id: int, temp_url: str):
        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})

        folder_path = self._get_user_dir(user_id, appeal_id)
        file_name = temp_url.split('/')[-1]
        file_path = os.path.join(folder_path, file_name)

        await self._save_photo_to_disk(file_path, temp_url)
        file_pathes: list = appeal_stash.setdefault('file_paths', [])
        file_pathes.append(file_path)

        permanent_url = await self._upload_photo(file_path, temp_url)
        permanent_urls: list = appeal_stash.setdefault('urls', [])
        permanent_urls.append(permanent_url)

        appeal_stash['file_paths'] = file_pathes
        appeal_stash['urls'] = permanent_urls
        user_stash[appeal_id] = appeal_stash
        self.storage[user_id] = user_stash

    def stash_page(self, user_id: int, appeal_id: int, title: str):
        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})
        page_tasks: list = appeal_stash.setdefault('page_tasks', [])

        storing_task = asyncio.create_task(
            self._create_page(user_id, appeal_id, title)
        )

        page_tasks.append(storing_task)
        appeal_stash['page_tasks'] = page_tasks
        user_stash[appeal_id] = appeal_stash
        self.storage[user_id] = user_stash

    async def _create_page(self, user_id: int, appeal_id: int, title: str):
        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})
        photo_tasks: list = appeal_stash.setdefault('photo_tasks', [])

        await asyncio.gather(*photo_tasks)

        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})

        page_url = await self.telegraph.create_page(appeal_stash['urls'],
                                                    title)
        appeal_stash['page_url'] = page_url

        user_stash[appeal_id] = appeal_stash
        self.storage[user_id] = user_stash

    async def get_photo_data(self, user_id: int, appeal_id: int) -> dict:
        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})

        if not appeal_stash:
            return appeal_stash

        page_tasks = appeal_stash.get('page_tasks', [])
        photo_tasks = appeal_stash.get('photo_tasks', [])
        await asyncio.gather(*(page_tasks + photo_tasks))

        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})

        return appeal_stash

    def _get_user_dir(self, user_id: int, appeal_id: int) -> str:
        dir_path = os.path.join(self.files_dir, str(user_id), str(appeal_id))

        try:
            os.makedirs(dir_path)
            return dir_path
        except FileExistsError:
            return dir_path

    async def clear_storage(self, user_id: int, appeal_id: int) -> None:
        user_stash: dict = self.storage.get(user_id, {})
        appeal_stash: dict = user_stash.get(appeal_id, {})

        page_tasks = appeal_stash.get('page_tasks', [])
        photo_tasks = appeal_stash.get('photo_tasks', [])
        await asyncio.gather(*(page_tasks + photo_tasks))

        user_stash.pop(appeal_id, None)

        if not user_stash:
            self.storage.pop(user_id, None)

        shutil.rmtree(self._get_user_dir(user_id, appeal_id),
                      ignore_errors=True)

    async def get_permanent_url(self,
                                url: str,
                                user_id: int,
                                appeal_id: int) -> Tuple[str, str]:
        file_path = os.path.join(self._get_user_dir(user_id, appeal_id),
                                 url.split('/')[-1])

        await self._save_photo_to_disk(file_path, url)
        permanent_url = await self._upload_photo(file_path, url)
        return permanent_url, file_path

    async def _upload_photo(self, file_path: str, temp_url: str) -> str:
        file_id = await self._upload_file(file_path)

        if file_id:
            full_path = 'https://telegra.ph' + file_id
        else:
            full_path = temp_url

        return full_path

    async def _upload_file(self, file_path: str) -> str:
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

                async with aiohttp.ClientSession() as http_session:
                    async with http_session.post(upload_url, data=form) as r:
                        result = await r.json()

            if isinstance(result, dict) and 'error' in result:
                if tries != 0:
                    await asyncio.sleep(1)
                    tries -= 1
                else:
                    uploaded = True
            else:
                uploaded = True
                file_id = result[0]['src']

        return file_id

    async def _save_photo_to_disk(self, file_path: str, url: str):
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url) as resp:
                raw_file = await resp.content.read()

        with open(file_path, 'wb') as file:
            file.write(raw_file)
