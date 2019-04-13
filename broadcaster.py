from twitter import Twitter


class Broadcaster:
    def __init__(self, getter, locales):
        self.twitter = Twitter(getter, locales)

    async def share(self, data):
        await self.twitter.post(data)
