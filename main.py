import asyncio
import logging

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage
from aiogram.dispatcher import Dispatcher
from aiogram.utils import exceptions, executor
from aiogram.utils.markdown import text

import config

loop = asyncio.get_event_loop()
bot = Bot(token=config.API_TOKEN, loop=loop)

storage = RedisStorage(host=config.REDIS_HOST,
                       port=config.REDIS_PORT,
                       password=config.REDIS_PASSWORD)

dp = Dispatcher(bot, storage=storage)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    logging.info('Старт работы бота у пользователя ' +
                 str(message.from_user.id))

    line1 = 'Привет, этот бот помогает отсылать фото паркунов в ГАИ ' +\
            '... дописать про шаблон, про личные данные, про хранение обезличенных паркунов. ' +\
            'Работает пока что только в Минске.'

    instructions = text(line1)

    await bot.send_message(message.chat.id,
                           instructions)


@dp.message_handler()
async def process_text(message: types.Message):
    user_text = message.text.strip()

    logging.info('Пользователь ' + str(message.from_user.id) +
                 ' cпросил ' + user_text + '.')

    await bot.send_message(message.chat.id, user_text)


async def startup(dispatcher: Dispatcher):
    logging.info('Старт бота.')


async def shutdown(dispatcher: Dispatcher):
    logging.info('Убиваем бота.')

    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


def main():
    executor.start_polling(dp,
                           loop=loop,
                           skip_updates=True,
                           on_startup=startup,
                           on_shutdown=shutdown)


if __name__ == '__main__':
    main()
