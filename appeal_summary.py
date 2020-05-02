from typing import Callable, Dict, Optional
import config
import re
from locales import Locales
from aiogram.dispatcher.storage import FSMContextProxy


class AppealSummary():
    def __init__(self,
                 locales: Locales,
                 get_sender_full_name: Callable,
                 get_value: Callable,
                 get_sender_address: Callable):
        self.locales = locales
        self.get_sender_full_name = get_sender_full_name
        self.get_value = get_value
        self.get_sender_address = get_sender_address

    def get_vehicle_number(self, language: str) -> str:
        vehicle_number_str = self.locales.text(language, 'violation_plate')
        location_str = self.locales.text(language, 'violation_location')

        vehicle_number = \
            rf"(?:{vehicle_number_str}\s*)(?P<plate>.+?)" + \
            rf"(?:\s*{location_str}\s*)"

        return vehicle_number

    def get_violation_address(self, language: str) -> str:
        location_str = self.locales.text(language, 'violation_location')
        datetime_str = self.locales.text(language, 'violation_datetime')

        violation_address = \
            rf"(?:\s*{location_str}\s*)(?P<address>.+?)" + \
            rf"(?:\s*{datetime_str}\s*)"

        return violation_address

    def get_violation_caption(self, language: str) -> str:
        caption_str = self.locales.text(language, 'caption')
        channel_url = config.CHANNEL.replace('@', 'https://t.me/')

        channel_warning_str = \
            self.locales.text(language,
                              'channel_warning').format(channel_url,
                                                        config.TWI_URL,
                                                        config.VK_URL)[:15]

        violation_caption = \
            rf"(?:\s*{caption_str}\s*)(?P<caption>(.|\s)+?)" + \
            rf"(?:\s*{channel_warning_str})"

        return violation_caption

    def get_violation_recipient(self, language: str) -> str:
        recipient_str = self.locales.text(language, 'recipient')
        bot_lang_str = self.locales.text(language, 'letter_lang')[:10]

        violation_recipient = \
            rf"(?:\s*{recipient_str}\s*)(?P<recipient>(.|\s)+?)" +\
            rf"(?:\s*{bot_lang_str})"

        return violation_recipient

    def get_violation_datetime(self, language: str) -> str:
        datetime_str = self.locales.text(language, 'violation_datetime')
        caption_str = self.locales.text(language, 'caption')
        channel_url = config.CHANNEL.replace('@', 'https://t.me/')

        channel_warning_str = \
            self.locales.text(language,
                              'channel_warning').format(channel_url,
                                                        config.TWI_URL,
                                                        config.VK_URL)[:15]

        violation_datetime = \
            rf"(?:\s*{datetime_str}\s*)(?P<datetime>.+?)" + \
            rf"(?:\s*({caption_str}|{channel_warning_str})\s*)"

        return violation_datetime

    def parse_violation_data(
            self,
            language: str,
            summary: str) -> Optional[Dict[str, str]]:
        cleaned = summary.replace('\n', ' ')

        match_vehicle_number = re.search(self.get_vehicle_number(language),
                                         cleaned,
                                         re.MULTILINE | re.IGNORECASE)

        match_violation_address = re.search(
            self.get_violation_address(language),
            cleaned,
            re.MULTILINE | re.IGNORECASE)

        match_violation_datetime = re.search(
            self.get_violation_datetime(language),
            cleaned,
            re.MULTILINE | re.IGNORECASE)

        match_violation_caption = re.search(
            self.get_violation_caption(language),
            cleaned,
            re.MULTILINE | re.IGNORECASE)

        match_violation_recipient = re.search(
            self.get_violation_recipient(language),
            cleaned,
            re.MULTILINE | re.IGNORECASE)

        if not (match_vehicle_number and
                match_violation_address and
                match_violation_datetime and
                match_violation_recipient):
            return None

        if match_violation_caption:
            caption = match_violation_caption.group('caption')
        else:
            caption = ''

        return {
            'violation_vehicle_number': match_vehicle_number.group('plate'),
            'violation_address': match_violation_address.group('address'),
            'violation_datetime': match_violation_datetime.group('datetime'),
            'violation_caption': caption,
            'violation_recipient': match_violation_recipient.group('recipient')
        }

    async def compose_summary(self, language: str,  data: FSMContextProxy):
        recipient_name = self.locales.text(
            language, self.get_value(data, 'recipient'))

        channel_url = config.CHANNEL.replace('@', 'https://t.me/')

        text = self.locales.text(language, 'check_please') + '\n' +\
            '\n' +\
            self.locales.text(language, 'recipient') +\
            f" <b>{recipient_name}</b>" + '\n' +\
            self.locales.text(language, 'letter_lang').format(
                self.locales.text(language,
                                  'lang' + self.get_value(data,
                                                          'letter_lang'))) +\
            '\n' +\
            '\n' +\
            self.locales.text(language, 'sender') + '\n' +\
            self.locales.text(language, 'sender_name') +\
            ' <b>{}</b>'.format(self.get_sender_full_name(data)) + '\n' +\
            self.locales.text(language, 'sender_email') +\
            ' <b>{}</b>'.format(self.get_value(data, 'sender_email')) + '\n' +\
            self.locales.text(language, 'sender_phone') +\
            ' <b>{}</b>'.format(self.get_value(data, 'sender_phone')) + '\n' +\
            self.locales.text(language, 'sender_address') +\
            ' <b>{}</b>'.format(self.get_sender_address(data)) + '\n' +\
            self.locales.text(language, 'sender_zipcode') +\
            ' <b>{}</b>'.format(self.get_value(data, 'sender_zipcode')) + \
            '\n' +\
            '\n' +\
            self.locales.text(language, 'violator') + '\n' +\
            self.locales.text(language, 'violation_plate') +\
            f' <b>{self.get_value(data, "violation_vehicle_number")}</b>' + \
            '\n' +\
            self.locales.text(language, 'violation_location') +\
            f' <b>{self.get_value(data, "violation_address")}</b>' + '\n' +\
            self.locales.text(language, 'violation_datetime') +\
            f' <b>{self.get_value(data, "violation_datetime")}</b>' + '\n' +\
            '\n' +\
            self.get_caption_text(data, language) +\
            self.locales.text(language,
                              'channel_warning').format(channel_url,
                                                        config.TWI_URL,
                                                        config.VK_URL)

        return text

    def get_caption_text(self, data: FSMContextProxy, language: str) -> str:
        caption = self.get_value(data, "violation_caption")

        if caption:
            return self.locales.text(language, 'caption') +\
                f' {self.get_value(data, "violation_caption")}' + '\n' +\
                '\n'
        else:
            return ''
