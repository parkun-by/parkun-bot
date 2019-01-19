import aiohttp
import config


class Geocoder():
    def __init__(self):
        self._http_session = aiohttp.ClientSession()

    def __del__(self):
        self._http_session.close()

    async def get_address(self, coordinates, language=config.RU):
        if language == config.RU:
            lang = 'ru_RU'
        elif language == config.BY:
            lang = 'be_BY'
        else:
            lang = 'ru_RU'

        params = (
            ('geocode', coordinates),
            ('kind', 'house'),
            ('format', 'json'),
            ('key', config.YANDEX_MAPS_API_KEY),
            ('lang', lang)
        )

        async with self._http_session.get(config.BASE_YANDEX_MAPS_URL,
                                          params=params) as response:
            if response.status != 200:
                return None

            resp_json = await response.json(content_type=None)
            address_array = resp_json['response']['GeoObjectCollection']

            try:
                address_bottom = address_array['featureMember'][0]

                address = address_bottom['GeoObject']['name'] + ', ' +\
                    address_bottom['GeoObject']['description']
            except IndexError:
                address = 'Не удалось подобрать адрес.'

            return address

        return None
