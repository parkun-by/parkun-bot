import aiohttp
import config
import json
from exceptions import ErrorWhilePutInQueue


class Rabbit:
    def __init__(self):
        self._http_session = aiohttp.ClientSession()

    def __del__(self):
        self._http_session.close()

    async def _send(self, exchange_name, body):
        url = config.RABBIT_ADDRESS + \
            f'/api/exchanges/parkun/{exchange_name}/publish'

        data = {
            'properties': {},
            'routing_key': 'violation',
            'payload': json.dumps(body),
            'payload_encoding': 'string'
        }

        async with self._http_session.post(url, json=data) as response:
            if response.status != 200:
                raise ErrorWhilePutInQueue(
                    f'Ошибка при отправке обращения: {response.reason}')

    async def send_appeal(self, body):
        await self._send(config.RABBIT_EXCHANGE_APPEAL, body)

    async def send_sharing(self, body):
        await self._send(config.RABBIT_EXCHANGE_SHARING, body)

    async def get_captcha_url(self) -> str:
        url = config.RABBIT_ADDRESS + \
            f'/api/queues/parkun/{config.RABBIT_QUEUE_CAPTCHA_URL}/get'

        data = {
            'count': 1,
            'ackmode': 'ack_requeue_true',
            'encoding': 'auto',
        }

        async with self._http_session.post(url, json=data) as response:
            if response.status != 200:
                raise ErrorWhilePutInQueue(
                    f'Ошибка при отправке обращения: {response.reason}')

            print(await response.json())
