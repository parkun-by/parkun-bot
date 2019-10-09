import re


class Validator:
    def __init__(self):
        self.last_name = (
            re.compile(r"^[а-яА-ЯёЁЎўІі'\s-]+$", re.IGNORECASE),
            'bel_rus_only'
        )
        self.patronymic = self.first_name = self.last_name

        self.zipcode = (
            re.compile(r"^[0-9]+$", re.IGNORECASE),
            'digits_only'
        )

        self.city = self.last_name

        self.street = (
            re.compile(r"^[а-яА-ЯёЁЎўІі'0-9.,\-\s]+$", re.IGNORECASE),
            'bel_rus_digits_only'
        )

        self.building = self.street

    def valid(self, text, regex, error_message):
        if regex.match(text) is None:
            return error_message
        else:
            return ''
