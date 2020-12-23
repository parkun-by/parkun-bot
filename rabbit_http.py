from typing import Optional
import aiohttp
import config
import json
from exceptions import *

PERSISTENT = 2


class Rabbit:
    async def _send(self,
                    exchange_name: str,
                    routing_key: str,
                    body: dict) -> None:
        url = config.RABBIT_HTTP_ADDRESS + \
            f'/api/exchanges/%2F/{exchange_name}/publish'

        data = {
            'properties': {
                'delivery_mode': PERSISTENT,
            },
            'routing_key': routing_key,
            'payload': json.dumps(body),
            'payload_encoding': 'string'
        }

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(url, json=data) as response:
                if response.status != 200:
                    raise ErrorWhilePutInQueue(
                        f'Ошибка при отправке обращения: {response.reason}')

    async def send_appeal(self,
                          appeal: dict,
                          user_id: int) -> None:
        body = {
            'type': config.APPEAL,
            'appeal': appeal,
            'appeal_id': appeal['appeal_id'],
            'user_id': user_id,
            'sender_email': appeal['sender_email'],
            'sender_email_password': appeal['sender_email_password'],
        }

        await self._send(config.RABBIT_EXCHANGE_MANAGING,
                         config.RABBIT_ROUTING_APPEAL_TO_QUEUE,
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

        await self._send(config.RABBIT_EXCHANGE_SENDING,
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
                                appeal_email: Optional[str],
                                routing_key: str) -> None:
        body = {
            'type': config.CAPTCHA_TEXT,
            'captcha_text': captcha_text,
            'user_id': user_id,
            'appeal_id': appeal_id,
            'sender_email': appeal_email,
        }

        await self._send(config.RABBIT_EXCHANGE_SENDING,
                         routing_key,
                         body)
