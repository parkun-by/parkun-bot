import config
import asyncio
import aiofiles

# NOTE: the package name is peony and not peony-twitter
from peony import PeonyClient


class Twitter:
    def __init__(self, getter, locales):
        self.client = PeonyClient(
            consumer_key=config.CONSUMER_KEY,
            consumer_secret=config.CONSUMER_SECRET,
            access_token=config.ACCESS_TOKEN,
            access_token_secret=config.ACCESS_TOKEN_SECRET)

        self.get_param = getter
        self.locales = locales

    async def post(self, data):
        language = self.get_param(data, 'ui_lang')
        file_paths = self.get_param(data, 'photo_files_paths')

        caption = self.locales.text(language, 'violation_datetime') +\
            ' {}'.format(self.get_param(data, 'violation_datetime')) + '\n' +\
            self.locales.text(language, 'violation_location') +\
            ' {}'.format(self.get_param(data, 'violation_location')) + '\n' +\
            self.locales.text(language, 'violation_plate') + \
            ' {}'.format(self.get_param(data, 'vehicle_number'))

        media_ids = []

        for file_path in file_paths:
                uploaded = await self.client.upload_media(file_path,
                                                          chunk_size=2**18,
                                                          chunked=True)
                media_ids.append(uploaded.media_id)

        await self.client.api.statuses.update.post(status=caption,
                                                   media_ids=media_ids)

        # print(file_paths)
        # await self.client.api.statuses.update.post(status="I'm using Peony!!")
