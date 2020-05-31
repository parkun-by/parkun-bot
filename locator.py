from asyncio.events import AbstractEventLoop
import asyncio
import aiohttp
import config
import json
import territory
import logging
from scheduler import Scheduler, RELOAD_BOUNDARY
from random import randint
import datetime_parser


logger = logging.getLogger(__name__)


class Locator:
    def __init__(self, loop: AbstractEventLoop):
        self._timeout = aiohttp.ClientTimeout(connect=5)
        self._boundaries = {}
        self.loop = loop
        self.scheduler: Scheduler
        self.bot_id: int = 0

    async def get_boundary(self,
                           region: str,
                           try_counter=5) -> None:
        region_name = config.OSM_REGIONS[region]
        url = 'http://nominatim.openstreetmap.org/search?'

        params = (
            ('format', 'json'),
            ('q', region_name),
            ('polygon_geojson', 1)
        )

        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(url,
                                            params=params,
                                            timeout=self._timeout) as response:
                    if response.status != 200:
                        return None

                    resp_json = await response.json(content_type=None)
                    boundary = resp_json[0]['geojson']['coordinates'][0]

        except aiohttp.client_exceptions.ServerTimeoutError:
            boundary = []

        except aiohttp.client_exceptions.ClientOSError:
            boundary = []

        except json.JSONDecodeError:
            boundary = []

        except IndexError:
            boundary = []

        except Exception:
            logger.exception(f"Ошибка при загрузке региона")
            boundary = []

        if not boundary:
            await asyncio.sleep(5)

            if try_counter > 0:
                logger.info(f"Еще одна попытка для региона {region}")
                await self.get_boundary(region, try_counter - 1)
            else:
                logger.warning(f"Закончились попытки для региона {region}")
                asyncio.ensure_future(self.download_boundary_later(region))
                self._boundaries[region] = []

        else:
            logger.info(f"Загружены границы региона {region}")
            self._boundaries[region] = boundary

    async def download_boundary_later(self, region: str):
        task = {
            'user_id': self.bot_id,
            'executor': RELOAD_BOUNDARY,
            'kvargs': {
                'region': region,
            },
            'execute_time': datetime_parser.get_current_datetime_str(
                shift_hours=config.DEFAULT_SCHEDULER_PAUSE)
        }

        await self.scheduler.add_task(task)

    async def download_boundaries(self):
        tasks = []

        for region in config.OSM_REGIONS:
            task = asyncio.ensure_future(self.get_boundary(region))
            tasks.append(task)
            await asyncio.sleep(1)

        asyncio.gather(*tasks)

    def __point_is_in_polygon(self, boundary, longitude, latitude):
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
        """Если регион разбит на части, то будем возвращать каждую"""
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

    async def get_region(self, coordinates, region=None):
        if not isinstance(coordinates, list):
            return None

        for region in territory.regions(region):
            if region not in self._boundaries:
                continue

            areas = self.__areas_in_region(self._boundaries[region])

            for area in areas:
                if self.__point_is_in_polygon(area,
                                              coordinates[0],
                                              coordinates[1]):
                    if territory.has_subregions(region):
                        return await self.get_region(coordinates, region)
                    else:
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
            ('apikey', config.YANDEX_MAPS_API_KEY),
            ('lang', lang)
        )

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(config.BASE_YANDEX_MAPS_URL,
                                        params=params) as response:
                if response.status != 200:
                    return None

                resp_json = await response.json(content_type=None)
                address_array = resp_json['response']['GeoObjectCollection']

                try:
                    address_bottom = \
                        address_array['featureMember'][0]['GeoObject']

                    address = address_bottom['name'] + ', ' +\
                        address_bottom['description']
                except IndexError:
                    address = config.ADDRESS_FAIL

                return address

    async def get_coordinates(self, address):
        params = (
            ('apikey', config.YANDEX_MAPS_API_KEY),
            ('geocode', address),
            ('kind', 'house'),
            ('format', 'json'),
        )

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(config.BASE_YANDEX_MAPS_URL,
                                        params=params) as response:
                if response.status != 200:
                    return None

                resp_json = await response.json(content_type=None)
                address_array = resp_json['response']['GeoObjectCollection']

                try:
                    address_bottom = \
                        address_array['featureMember'][0]['GeoObject']

                    str_coordinates = address_bottom['Point']['pos']
                    str_coordinates = str_coordinates.split(' ')

                    coordinates = [float(str_coordinates[0]),
                                   float(str_coordinates[1])]
                except IndexError:
                    return None

                return coordinates
