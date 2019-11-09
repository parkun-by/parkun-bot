import aiohttp
import requests
import tempfile
import os
import shutil


class Uploader:
    def __init__(self):
        self._http_session = aiohttp.ClientSession()
        self.tempdir = tempfile.mkdtemp('_parkun')

    def __del__(self):
        self._http_session.close()
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _get_user_dir(self, user_id: int, appeal_id: int) -> str:
        dir_path = os.path.join(self.tempdir, str(user_id), str(appeal_id))

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
                                appeal_id: int) -> (str, str):
        filename = os.path.join(self._get_user_dir(user_id, appeal_id),
                                url.split('/')[-1])

        async with self._http_session.get(url) as resp:
            raw_file = await resp.content.read()

        with open(filename, 'wb') as file:
            file.write(raw_file)

        with open(filename, 'rb') as file:
            upload_url = 'https://telegra.ph/upload'
            files = {'file': ('file', file, 'image/jpg')}
            result = requests.post(upload_url, files=files).json()

        try:
            full_path = 'https://telegra.ph' + result[0]['src']
        except Exception:
            full_path = url

        return full_path, filename
