from aioimaplib import aioimaplib


class Email:
    def __init__(self, loop):
        self.client = aioimaplib.IMAP4_SSL(host='imap-mail.outlook.com',
                                           port=993,
                                           loop=loop)

    async def check_connection(self, email: str, password: str) -> bool:
        await self.client.wait_hello_from_server()
        await self.client.login(email, password)
        client_state = self.client.get_state()
        await self.client.logout()

        if client_state == 'AUTH':
            return True
        else:
            return False
