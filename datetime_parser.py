import pytz
from datetime import datetime, timedelta
from typing import Optional, Tuple
import re


FULL_DATETIME = r"^\s*(?:" + \
    r"(1[0-9]|2[0-9]|3[01]|0?[1-9])" + \
    r"(?:\s*|\s*\.\s*)" + \
    r"(1[012]|0?[1-9])" + \
    r"(?:\s*|\s*\.\s*)" + \
    r"([0-9]{4}|[0-9]{2})" + \
    r"(?:\s*)" + \
    r")??" + \
    r"(?:" + \
    r"(1\d|2[0-3]|0?\d)" + \
    r"(?:\s*|\s*\-\s*|\s*\:\s*)" + \
    r"([1-5]\d|0?\d)" + \
    r")\s*$"


datetime_regexp = re.compile(FULL_DATETIME)


def get_current_datetime(shift_days=0) -> str:
    tz_minsk = pytz.timezone('Europe/Minsk')
    current_datetime = datetime.now(tz_minsk) + timedelta(days=shift_days)
    return current_datetime.isoformat()


def get_violation_datetime(saved_datetime: str,
                           entered_datetime: str) -> Optional[str]:
    year = 0
    month = 0
    day = 0
    hour = 0
    minute = 0

    if not datetime_regexp.match(entered_datetime):
        return None

    splitted = datetime_regexp.split(entered_datetime)

    if splitted[4]:
        hour = int(splitted[4])

    if splitted[5]:
        minute = int(splitted[5])

    try:
        day = int(splitted[1])
        month = int(splitted[2])
        year = int(splitted[3])
    except Exception:
        day, month, year = parse_datetime(saved_datetime or
                                          get_current_datetime())

    day = str(day).rjust(2, '0')
    month = str(month).rjust(2, '0')
    year = str(year).rjust(2, '0')
    hour = str(hour).rjust(2, '0')
    minute = str(minute).rjust(2, '0')

    return f'{day}.{month}.{year} {hour}:{minute}'


def parse_datetime(datetime_iso: str) -> Tuple[str, str, str]:
    datetime_to_split = datetime.fromisoformat(datetime_iso)

    return str(datetime_to_split.day), \
        str(datetime_to_split.month), \
        str(datetime_to_split.year)
