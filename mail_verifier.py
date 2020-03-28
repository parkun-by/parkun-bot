import aiohttp
import config


class MailVerifier:
    async def verify(self, email, language):
        params = (
            ('address', email),
            ('language', language),
        )

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(config.MAIL_VERIFIER_URL,
                                        params=params) as response:
                return await response.text()
