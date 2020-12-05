import logging
from typing import List

import aiohttp

import config

logger = logging.getLogger(__name__)


async def recognize_numberplates(path: str) -> List[str]:
    if not config.NUMBERPLATES_RECOGNIZER_ENABLED:
        return list()

    url = config.NUMBERPLATES_RECOGNIZER_URL
    data = {'path': path}

    async with aiohttp.ClientSession() as http_session:
        async with http_session.post(url, json=data) as response:
            try:
                result = await response.json()
                numberplates = format_raw_numbers(result['data'])
                return numberplates
            except Exception:
                logger.exception('Numberplate recognition error')
                return list()


def format_raw_numbers(raw_numbers: List[str]) -> List[str]:
    """
    Recognizer provider numberplates without formatting (spaces, dashes, etc).
    The function formattes numbers and pushes out incorrect (unformattable)
    ones.
    """
    # TODO приделать регулярки и форматирование
    return raw_numbers
