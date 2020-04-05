import logging
import aiohttp
import asyncio
import os
import shutil
import secrets

from typing import Tuple


logger = logging.getLogger(__name__)


class PhotoManager:
    def __init__(self):
        self.files_dir = os.path.join('/tmp', 'temp_files_parkun')

        try:
            os.makedirs(self.files_dir)
        except FileExistsError:
            pass

    def __del__(self):
        shutil.rmtree(self.files_dir, ignore_errors=True)

    def _get_user_dir(self, user_id: int, appeal_id: int) -> str:
        dir_path = os.path.join(self.files_dir, str(user_id), str(appeal_id))

        try:
            os.makedirs(dir_path)
            return dir_path
        except FileExistsError:
            return dir_path

    def clear_storage(self, user_id: int, appeal_id: int) -> None:
        shutil.rmtree(self._get_user_dir(user_id, appeal_id),
                      ignore_errors=True)

    def get_file_list(self, user_id: int, appeal_id: int) -> list:
        return os.listdir(self._get_user_dir(user_id, appeal_id))

    async def get_permanent_url(self,
                                url: str,
                                user_id: int,
                                appeal_id: int) -> Tuple[str, str]:
        file_path = os.path.join(self._get_user_dir(user_id, appeal_id),
                                 url.split('/')[-1])

        await self.save_photo_to_disk(file_path, url)
        permanent_url = await self.upload_photo(file_path, url)
        return permanent_url, file_path

    async def upload_photo(self, file_path: str, temp_url: str) -> str:
        file_id = await self.upload_file(file_path)

        if file_id:
            full_path = 'https://telegra.ph' + file_id
        else:
            full_path = temp_url

        return full_path

    async def upload_file(self, file_path: str) -> str:
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

    async def save_photo_to_disk(self, file_path: str, url: str):
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url) as resp:
                raw_file = await resp.content.read()

        with open(file_path, 'wb') as file:
            file.write(raw_file)
