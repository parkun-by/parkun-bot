import logging
import re
from typing import List, Match, Optional

import aiohttp

import config

logger = logging.getLogger(__name__)

GENERAL = 'general'
CARGO = 'cargo'
TRANSIT = 'transit'
POLICE = 'police'
TAXI = 'taxi'

NUMBER = 'number'
LETTERS = 'letters'
REGION = 'region'

FORMATS = {
    GENERAL: f'{NUMBER} {LETTERS}-{REGION}',
    CARGO: f'{LETTERS} {NUMBER}-{REGION}',
    TRANSIT: f'{REGION}{LETTERS} T {NUMBER}',
    POLICE: f'{NUMBER}{LETTERS}',
    TAXI: f'{REGION} TAX {NUMBER}',
}

KEYWORDS = {
    GENERAL: (NUMBER, LETTERS, REGION),
    CARGO: (LETTERS, NUMBER, REGION),
    TRANSIT: (REGION, LETTERS, NUMBER),
    POLICE: (NUMBER, LETTERS),
    TAXI: (REGION, NUMBER),
}

PATTERNS = {
    GENERAL: re.compile(
        rf"^(?P<{NUMBER}>\d\d\d\d)"
        rf"(?P<{LETTERS}>[А-ЯA-Z][А-ЯA-Z])"
        rf"(?P<{REGION}>\d)$"
    ),

    CARGO: re.compile(
        rf"^(?P<{LETTERS}>[А-ЯA-Z][А-ЯA-Z])"
        rf"(?P<{NUMBER}>\d\d\d\d)"
        rf"(?P<{REGION}>\d)$"
    ),

    TRANSIT: re.compile(
        rf"^(?P<{REGION}>\d)"
        rf"(?P<{LETTERS}>[А-ЯA-Z][А-ЯA-Z])T"
        rf"(?P<{NUMBER}>\d\d\d\d)$"
    ),

    POLICE: re.compile(
        rf"^(?P<{NUMBER}>\d\d\d\d)"
        rf"(?P<{LETTERS}>[А-ЯA-Z][А-ЯA-Z])$"
    ),

    TAXI: re.compile(rf"^(?P<{REGION}>\d)TAX(?P<{NUMBER}>\d\d\d\d)$"),
}


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
    Recognizer provides numberplates without formatting (spaces, dashes, etc).
    The function formattes numbers and pushes out incorrect (unformattable)
    ones.
    """
    formatted_numbers = list()

    for number in raw_numbers:
        if formatted := format_number(number):
            formatted_numbers.append(formatted)

    return formatted_numbers


def format_number(raw_number: str) -> Optional[str]:
    """
    Formattes number or return nothing if number is unformattable.
    """
    for pattern_name in PATTERNS:
        if matched_numbers := list(
            PATTERNS[pattern_name].finditer(raw_number)
        ):
            matched_number = matched_numbers[0]

            formatted_number = put_parts_to_template(pattern_name,
                                                     matched_number)
            return formatted_number

    return None


def put_parts_to_template(pattern: str, matched_number: Match[str]) -> str:
    template = FORMATS[pattern]

    for keyword in KEYWORDS[pattern]:
        template = template.replace(keyword, matched_number.group(keyword))

    return template
