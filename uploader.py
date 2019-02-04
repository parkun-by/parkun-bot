import aiohttp
import requests
import tempfile


class Uploader:
    def __init__(self):
        self._http_session = aiohttp.ClientSession()

    def __del__(self):
        self._http_session.close()

    async def get_permanent_url(self, url):
        filename = tempfile.gettempdir() + '/' + url.split('/')[-1]

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

        return full_path
