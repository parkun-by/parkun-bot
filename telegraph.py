import config
import pytz
import json

from aio_telegraph.api import TelegraphAPIClient
from asyncio.events import AbstractEventLoop
from datetime import datetime
from typing import Optional


class Telegraph():
    def __init__(self, loop: AbstractEventLoop):
        self.__api = TelegraphAPIClient()
        self.__api.ACCESS_TOKEN = config.TPH_ACCESS_TOKEN
        self.__api.loop = loop

    async def create_page(self, photos: list) -> Optional[str]:
        title = self._get_title()
        content = self._get_content(photos)
        page: dict = await self.__api.create_page(title,
                                                  content,
                                                  return_content='False')

        url = page.get('result', {}).get('url', None)
        return url

    def _get_title(self) -> str:
        tz_minsk = pytz.timezone('Europe/Minsk')
        now = datetime.now(tz_minsk)
        minute = str(now.minute)
        hour = str(now.hour)
        short_year = str(now.year)[-2:]

        return hour + minute + short_year

    def _get_content(self, photos: list) -> str:
        content = []

        for photo in photos:
            content.append(self._get_photo_elem(photo))

        return json.dumps(content)

    def _get_photo_elem(self, image_url: str):
        return {
            "tag": "img",
            "attrs": {
                "src": image_url
            },
        }
