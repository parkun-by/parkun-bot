import aiohttp
import config
import json


class Locator():
    def __init__(self):
        self._timeout = aiohttp.ClientTimeout(connect=5)
        self._http_session = aiohttp.ClientSession()
        self._boundaries = {}

    def __del__(self):
        self._http_session.close()

    async def __get_boundary(self, http_session, region_name):
        url = 'http://nominatim.openstreetmap.org/search?'

        params = (
            ('format', 'json'),
            ('q', region_name),
            ('polygon_geojson', 1)
        )

        try:
            async with http_session.get(url,
                                        params=params,
                                        timeout=self._timeout) as response:
                if response.status != 200:
                    return None

                resp_json = await response.json(content_type=None)
                boundary = resp_json[0]['geojson']['coordinates'][0]

        except aiohttp.client_exceptions.ServerTimeoutError:
            boundary = []

        except json.decoder.JSONDecodeError:
            boundary = []

        except IndexError:
            boundary = []

        return boundary

    async def download_boundaries(self):
        self._boundaries = {
            config.MINSK:
                await self.__get_boundary(self._http_session,
                                          'Minsk, Belarus'),

            config.BREST_REGION:
                await self.__get_boundary(self._http_session,
                                          'Brest Region, Belarus'),

            config.VITSEBSK_REGION:
                await self.__get_boundary(self._http_session,
                                          'Vitsebsk Region, Belarus'),

            config.HOMEL_REGION:
                await self.__get_boundary(self._http_session,
                                          'Homel Region, Belarus'),

            config.HRODNA_REGION:
                await self.__get_boundary(self._http_session,
                                          'Hrodna Region, Belarus'),

            config.MINSK_REGION:
                await self.__get_boundary(self._http_session,
                                          'Minsk Region, Belarus'),

            config.MAHILEU_REGION:
                await self.__get_boundary(self._http_session,
                                          'Mahilyow Region, Belarus'),
        }

    def __point_is_in_polygon(self, boundary, longitude, latitude):
        i = 0
        overlap = False
        vertices_amount = len(boundary)
        j = vertices_amount - 1

        for i in range(vertices_amount - 1):
            if (((boundary[i][0] > longitude) !=
                    (boundary[j][0] > longitude)) and
                (latitude <
                    (boundary[j][1] - boundary[i][1]) *
                    (longitude - boundary[i][0]) /
                    (boundary[j][0] - boundary[i][0]) + boundary[i][1])):
                overlap = not overlap

            j = i

        return overlap

    def __areas_in_region(self, boundaries):
        '''Если регион разбит на части, то будем возвращать каждую'''
        try:
            if isinstance(boundaries[0][0], list):
                for boundary in boundaries:
                    if isinstance(boundary[0][0], list):
                        yield self.__areas_in_region(boundary)
                    else:
                        yield boundary
            else:
                yield boundaries
        except IndexError:
            yield []

    async def get_region(self, coordinates):
        if not isinstance(coordinates, list):
            return None

        for region in self._boundaries:
            areas = self.__areas_in_region(self._boundaries[region])

            for area in areas:
                if self.__point_is_in_polygon(area,
                                              coordinates[0],
                                              coordinates[1]):
                    return region

    async def get_address(self, coordinates, language=config.RU):
        coordinates = (str(coordinates[0]) + ', ' + str(coordinates[1]))

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
                address_bottom = address_array['featureMember'][0]['GeoObject']

                address = address_bottom['name'] + ', ' +\
                    address_bottom['description']
            except IndexError:
                address = config.ADDRESS_FAIL

            return address

        return None

    async def get_coordinates(self, address):
        params = (
            ('geocode', address),
            ('kind', 'house'),
            ('format', 'json'),
            ('key', config.YANDEX_MAPS_API_KEY),
        )

        async with self._http_session.get(config.BASE_YANDEX_MAPS_URL,
                                          params=params) as response:
            if response.status != 200:
                return None

            resp_json = await response.json(content_type=None)
            address_array = resp_json['response']['GeoObjectCollection']

            try:
                address_bottom = address_array['featureMember'][0]['GeoObject']
                str_coordinates = address_bottom['Point']['pos']
                str_coordinates = str_coordinates.split(' ')

                coordinates = [float(str_coordinates[0]),
                               float(str_coordinates[1])]
            except IndexError:
                return None

            return coordinates

        return None
