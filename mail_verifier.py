import aiohttp
import config


class MailVerifier:
    def __init__(self):
        self._http_session = aiohttp.ClientSession()

    def __del__(self):
        self._http_session.close()

    async def verify(self, email, language):
        params = (
            ('address', email),
            ('language', language),
        )

        async with self._http_session.get(config.MAIL_VERIFIER_URL,
                                          params=params) as response:
            return await response.text()
