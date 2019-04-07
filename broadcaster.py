from twitter import Twitter


class Broadcaster:
    def __init__(self):
        self.twitter = Twitter()

    async def share(self, message):
        await self.twitter.post(message)
