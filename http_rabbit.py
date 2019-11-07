import aiohttp
import config
import json
from exceptions import *


class Rabbit:
    def __init__(self):
        self._http_session = aiohttp.ClientSession()

    def __del__(self):
        self._http_session.close()

    async def _send(self,
                    exchange_name: str,
                    routing_key: str,
                    body: dict) -> None:
        url = config.RABBIT_HTTP_ADDRESS + \
            f'/api/exchanges/%2F/{exchange_name}/publish'

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

    async def send_appeal(self,
                          appeal: dict,
                          user_id: int,
                          routing_key: str) -> None:
        body = {
            'type': config.APPEAL,
            'appeal': appeal,
            'appeal_id': appeal['appeal_id'],
            'user_id': user_id,
            'sender_email': appeal['sender_email'],
            'sender_email_password': appeal['sender_email_password'],
        }

        await self._send(config.RABBIT_EXCHANGE_APPEAL,
                         routing_key,
                         body)

    async def send_cancel(self,
                          appeal_id: int,
                          user_id: int,
                          routing_key: str) -> None:
        body = {
            'type': config.CANCEL,
            'appeal_id': appeal_id,
            'user_id': user_id,
        }

        await self._send(config.RABBIT_EXCHANGE_APPEAL,
                         routing_key,
                         body)

    async def send_sharing(self, body: dict) -> None:
        await self._send(config.RABBIT_EXCHANGE_SHARING,
                         config.RABBIT_ROUTING_VIOLATION,
                         body)

    async def send_captcha_text(self,
                                captcha_text: str,
                                user_id: int,
                                appeal_id: int,
                                appeal_email: str or None,
                                routing_key: str) -> None:
        body = {
            'type': config.CAPTCHA_TEXT,
            'captcha_text': captcha_text,
            'user_id': user_id,
            'appeal_id': appeal_id,
            'sender_email': appeal_email,
        }

        await self._send(config.RABBIT_EXCHANGE_APPEAL,
                         routing_key,
                         body)

    async def ask_for_captcha_url(self,
                                  user_id: int,
                                  appeal_id: int,
                                  routing_key: str,
                                  email: str = None) -> None:
        body = {
            'type': config.GET_CAPTCHA,
            'appeal_id': appeal_id,
            'user_id': user_id,
            'sender_email': email,
        }

        await self._send(config.RABBIT_EXCHANGE_APPEAL,
                         routing_key,
                         body)

    async def get_captcha_url(self, preparer_queue: str) -> dict:
        url = config.RABBIT_HTTP_ADDRESS + \
            f'/api/queues/%2F/{preparer_queue}/get'

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

    async def get_preparer(self) -> str or None:
        url = config.RABBIT_HTTP_ADDRESS + \
            f'/api/queues/%2F/{config.RABBIT_QUEUE_TO_BOT}/get'

        data = {
            'count': 1,
            'ackmode': 'ack_requeue_false',
            'encoding': 'auto',
        }

        async with self._http_session.post(url, json=data) as response:
            if response.status != 200:
                raise ErrorWhilePutInQueue(
                    f'Ошибка при выборе обработчика: {response.reason}')

            try:
                data = json.loads((await response.json())[0]['payload'])
            except IndexError:
                return None

            return data['answer_queue']
