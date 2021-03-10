import config
import pytz
import json
import logging

from aio_telegraph.api import TelegraphAPIClient
from asyncio.events import AbstractEventLoop
from datetime import datetime
from typing import Optional


logger = logging.getLogger(__name__)


class Telegraph():
    def __init__(self, loop: AbstractEventLoop):
        self.__api = TelegraphAPIClient(access_token=config.TPH_ACCESS_TOKEN)
        self.__api.ACCESS_TOKEN = config.TPH_ACCESS_TOKEN

    async def create_page(self, photos: list, text: str) -> Optional[str]:
        title = self._get_title()
        content = self._get_content(photos, text)
        page: dict = await self.__api.create_page(title,
                                                  content,
                                                  return_content='False')
        try:
            url = page['result']['url']
            return url
        except Exception:
            logger.exception(f"Page creation failed: {str(page)}")
            return None

    def _get_title(self) -> str:
        tz_minsk = pytz.timezone('Europe/Minsk')
        now = datetime.now(tz_minsk)
        minute = str(now.minute)
        hour = str(now.hour)
        short_year = str(now.year)[-2:]

        return hour + minute + short_year

    def _get_content(self, photos: list, subtitle: str) -> str:
        content = [self._get_subtitle(subtitle)]

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

    def _get_subtitle(self, text: str) -> dict:
        return {
            'tag': 'p',
            'children': [text]
        }
