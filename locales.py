import json
import config
from typing import Optional


class Locales:
    def __init__(self):
        with open('localization.json') as file:
            self.__localization = json.load(file)

    def text(self, locale: str, text_id: str) -> str:
        return self.__localization[locale][text_id]

    def text_exists(self, key: str, text: str) -> bool:
        for locale in self.__localization:
            if text == self.__localization[locale][key]:
                return True

        return False

    def get_region_code(self, text: str) -> Optional[str]:
        for locale in self.__localization:
            for region in config.REGIONS:
                if text == self.__localization[locale][region]:
                    return region

        return None
