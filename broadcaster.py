from twitter import Twitter


class Broadcaster:
    def __init__(self, getter, locales):
        self.twitter = Twitter(getter, locales)

    async def share(self,
                    language: str,
                    file_paths: list,
                    coordinates: list,
                    date_time: str,
                    plate: str,
                    address: str) -> None:
        await self.twitter.post(language,
                                file_paths,
                                coordinates,
                                date_time,
                                plate,
                                address)
