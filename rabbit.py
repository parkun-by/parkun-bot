import aiohttp
import config
import json
from exceptions import ErrorWhilePutInQueue, NoCaptchaInQueue


class Rabbit:
    def __init__(self):
        self._http_session = aiohttp.ClientSession()

    def __del__(self):
        self._http_session.close()

    async def _send(self,
                    exchange_name: str,
                    routing_key: str,
                    body: dict) -> None:
        url = config.RABBIT_ADDRESS + \
            f'/api/exchanges/parkun/{exchange_name}/publish'

        data = {
            'properties': {},
            'routing_key': routing_key,
            'payload': json.dumps(body),
            'payload_encoding': 'string'
        }

        async with self._http_session.post(url, json=data) as response:
            if response.status != 200:
                raise ErrorWhilePutInQueue(
                    f'Ошибка при отправке обращения: {response.reason}')

    async def send_appeal(self, body: dict) -> None:
        await self._send(config.RABBIT_EXCHANGE_APPEAL,
                         config.RABBIT_ROUTING_VIOLATION,
                         body)

    async def send_sharing(self, body: dict) -> None:
        await self._send(config.RABBIT_EXCHANGE_SHARING,
                         config.RABBIT_ROUTING_VIOLATION,
                         body)

    async def send_captcha_text(self, body: dict, routing_key: str) -> None:
        await self._send(config.RABBIT_EXCHANGE_APPEAL,
                         routing_key,
                         body)

    async def get_captcha_url(self) -> dict:
        url = config.RABBIT_ADDRESS + \
            f'/api/queues/parkun/{config.RABBIT_QUEUE_CAPTCHA_URL}/get'

        data = {
            'count': 1,
            'ackmode': 'ack_requeue_false',
            'encoding': 'auto',
        }

        async with self._http_session.post(url, json=data) as response:
            if response.status != 200:
                raise ErrorWhilePutInQueue(
                    f'Ошибка при отправке обращения: {response.reason}')

            try:
                data = json.loads((await response.json())[0]['payload'])
            except IndexError:
                raise NoCaptchaInQueue()

            return data
