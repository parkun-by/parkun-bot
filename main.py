import asyncio
import copy
import io
import json
import logging
import re
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types.photo_size import PhotoSize
from aiogram.utils import executor
from aiogram.utils.exceptions import BadRequest as AiogramBadRequest
from aiogram.utils.exceptions import (CantTalkWithBots, ChatNotFound,
                                      MessageNotModified)
from dateutil import tz
from disposable_email_domains import blocklist

import config
import datetime_parser
import territory
import users
from appeal_summary import AppealSummary
from appeal_text import AppealText
from bot_storage import BotStorage
from imap_email import Email
from locales import Locales
from locator import Locator
from mail_verifier import MailVerifier
from photo_manager import PhotoManager
from photoitem import PhotoItem
from rabbit_amqp import Rabbit as AMQPRabbit
from rabbit_http import Rabbit as HTTPRabbit
from scheduler import CANCEL_ON_IDLE, RELOAD_BOUNDARY, Scheduler
from states import Form
from states_stack import StatesStack
from statistic import Statistic
from validator import Validator

Path("./logs").mkdir(parents=True, exist_ok=True)

file_handler_info = RotatingFileHandler("./logs/parkun_info.log",
                                        maxBytes=100000000,
                                        backupCount=5)
file_handler_info.setLevel(logging.INFO)

file_handler_error = RotatingFileHandler("./logs/parkun_error.log",
                                         maxBytes=10000000,
                                         backupCount=5)
file_handler_error.setLevel(logging.ERROR)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[file_handler_info, file_handler_error, stream_handler])

logger = logging.getLogger("parkun_bot")

loop = asyncio.get_event_loop()
bot = Bot(token=config.API_TOKEN, loop=loop)

storage = RedisStorage2(host=config.REDIS_HOST,
                        port=config.REDIS_PORT,
                        password=config.REDIS_PASSWORD)

dp = Dispatcher(bot, storage=storage)
mail_verifier = MailVerifier()
semaphore = asyncio.Semaphore()
locales = Locales()
validator = Validator()
rabbit_http = HTTPRabbit()
rabbit_amqp = AMQPRabbit()
photo_manager: PhotoManager
bot_storage: BotStorage
statistic: Statistic
scheduler: Scheduler
locator: Locator


def get_value(data: Union[FSMContextProxy, dict],
              key: str,
              placeholder: Any = None,
              read_only=False) -> Any:
    try:
        return get_text(data[key], placeholder)
    except KeyError:
        if not read_only:
            set_default(data, key)

        if placeholder is not None:
            return placeholder

        return data[key]


def pop_value(data: Union[FSMContextProxy, dict],
              key: str,
              placeholder: Any = None,
              read_only=False) -> Any:
    value = get_value(data, key, placeholder, read_only)
    data.pop(key)
    return value


def get_sender_address(data):
    city = commer(get_value(data, 'sender_city'))
    street = commer(get_value(data, 'sender_street'))
    house = commer(get_value(data, 'sender_house'))
    block = commer(get_value(data, 'sender_block'))
    flat = get_value(data, 'sender_flat')
    zipcode = commer(get_value(data, 'sender_zipcode'))

    if house:
        house = f'д.{house}'

    if block:
        block = f'корп.{block}'

    if flat:
        flat = f'кв.{flat}'

    return f'{zipcode}{city}{street}{house}{block}{flat}'.strip().strip(',')


def get_sender_full_name(data):
    first_name = get_value(data, "sender_first_name")
    last_name = get_value(data, "sender_last_name")
    patronymic = get_value(data, "sender_patronymic")

    return f'{first_name} {patronymic} {last_name}'.strip()


appeal_summary = AppealSummary(locales,
                               get_sender_full_name,
                               get_value,
                               get_sender_address)


async def get_ui_lang(state=None,
                      data: Optional[FSMContextProxy] = None) -> str:
    if data:
        return get_value(data, 'ui_lang')
    elif state:
        async with state.proxy() as my_data:
            return get_value(my_data, 'ui_lang')

    return config.RU


states_stack = StatesStack(dp, get_value, get_ui_lang, locales.text)


async def maybe_return_to_state(expected_state: str,
                                state_to_set: str,
                                user_id: int):
    state = dp.current_state(chat=user_id, user=user_id)
    current_state = await state.get_state()

    if current_state == expected_state:
        logger.info(f'Автовозврат в начальное состояние - {user_id}')
        await state.set_state(state_to_set)
    else:
        return

    language = await get_ui_lang(state)
    text = locales.text(language, "cancel_on_idle")
    text += "\n\n" + locales.text(language, state_to_set)
    await bot.send_message(user_id, text, disable_notification=True)


def commer(text: str) -> str:
    if text:
        return f'{text}, '

    return text


async def cancel_sending(user_id: int, appeal_id: int, text_id: str) -> None:
    logger.info(f'Время вышло - {user_id}')
    await pop_saved_state(user_id, user_id)
    state = dp.current_state(chat=user_id, user=user_id)

    async with state.proxy() as data:
        await delete_appeal_from_user_queue(data, user_id, appeal_id)
        language = await get_ui_lang(data=data)

    await invite_to_send_violation_again(language, user_id, appeal_id, text_id)


async def invite_to_send_violation_again(language: str,
                                         user_id: int,
                                         appeal_id: int,
                                         text_id: str) -> None:
    text = locales.text(language, text_id)

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    repeat_sending_button = types.InlineKeyboardButton(
        text=locales.text(language, 'approve_sending_button'),
        callback_data='/repeat_sending')

    keyboard.add(repeat_sending_button)

    try:
        await bot.send_message(user_id,
                               text,
                               reply_markup=keyboard,
                               reply_to_message_id=appeal_id)
    except AiogramBadRequest:
        await bot.send_message(user_id,
                               text,
                               reply_markup=keyboard)

REQUIRED_CREDENTIALS = [
    'sender_first_name',
    'sender_last_name',
    'sender_patronymic',
    'sender_email',
    'sender_city',
    'sender_zipcode',
    'sender_house',
]

SENDER_INFO = [
    Form.sender_first_name.state,
    Form.sender_patronymic.state,
    Form.sender_last_name.state,
    Form.sender_email.state,
    Form.sender_phone.state,
    Form.sender_city.state,
    Form.sender_street.state,
    Form.sender_block.state,
    Form.sender_house.state,
    Form.sender_flat.state,
    Form.sender_zipcode.state,
]

REVERSED_SENDER_INFO = copy.deepcopy(SENDER_INFO)
REVERSED_SENDER_INFO.reverse()

ADDITIONAL_MESSAGE = {
    Form.sender_email.state: 'nonexistent_email_warning',
    Form.sender_phone.state: 'phone_helps_to_police',
}

SOCIAL_NETWORKS = 'social_networks'
USERS = 'users'

BROADCAST_RECEIVERS = [
    SOCIAL_NETWORKS,
    USERS,
]

VIOLATION_INFO_KEYS = [
    'violation_attachments',
    'violation_photo_ids',
    'violation_photo_files_paths',
    'violation_photos_amount',
    'violation_vehicle_number',
    'violation_address',
    'violation_location',
    'violation_datetime',
    'violation_caption',
    'violation_date',
    'violation_photo_page',
]


def get_text(raw_text, placeholder):
    if not raw_text and placeholder:
        return placeholder

    return raw_text


async def invite_to_fill_credentials(chat_id, state):
    language = await get_ui_lang(state)
    text = locales.text(language, 'first_steps')

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    personal_info_button = types.InlineKeyboardButton(
        text=locales.text(language, 'send_personal_info'),
        callback_data='/enter_personal_info')

    settings_button = types.InlineKeyboardButton(
        text=locales.text(language, 'settings'),
        callback_data='/settings')

    keyboard.add(personal_info_button, settings_button)

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard)


async def invite_to_confirm_email(data, chat_id):
    language = await get_ui_lang(data=data)
    message = (locales.text(language, 'verify_email')).format(
        get_value(data, 'sender_email')
    )

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    verify_email_button = types.InlineKeyboardButton(
        text=locales.text(language, 'verify_email_button'),
        callback_data='/verify_email')

    keyboard.add(verify_email_button)

    await bot.send_message(chat_id,
                           message,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def send_appeal_textfile_to_user(appeal_text: str,
                                       language: str,
                                       user_id: int,
                                       appeal_id: int):
    appeal_text = convert_for_windows(appeal_text)
    file = io.StringIO(appeal_text)
    appeal_number = f'{str(appeal_id)}'
    file.name = locales.text(language, 'letter_html').format(appeal_number)
    await bot.send_document(user_id, file)


def convert_for_windows(appeal_text: str) -> str:
    return appeal_text.replace('\n', '\r\n')


def get_violation_caption(language: str,
                          date_time: str,
                          location: str,
                          plate: str) -> str:
    return locales.text(language, 'violation_datetime') +\
        ' {}'.format(date_time) + '\n' +\
        locales.text(language, 'violation_location') +\
        ' {}'.format(location) + '\n' +\
        locales.text(language, 'violation_plate') + \
        ' {}'.format(plate)


async def compose_appeal(data: FSMContextProxy,
                         user_id: int,
                         appeal_id: int) -> dict:
    appeal = {
        'type': config.APPEAL,
        'text': get_appeal_text(data, user_id, appeal_id),
        'police_department': get_value(data, 'recipient'),
        'sender_first_name': get_value(data, 'sender_first_name'),
        'sender_last_name': get_value(data, 'sender_last_name'),
        'sender_patronymic': get_value(data, 'sender_patronymic'),
        'sender_city': get_value(data, 'sender_city'),
        'sender_street': get_value(data, 'sender_street'),
        'sender_house': get_value(data, 'sender_house'),
        'sender_block': get_value(data, 'sender_block'),
        'sender_flat': get_value(data, 'sender_flat'),
        'sender_zipcode': get_value(data, 'sender_zipcode'),
        'sender_email': await get_appeal_email(data, user_id),
        'sender_email_password': get_value(data, 'sender_email_password'),
        'user_id': user_id,
        'appeal_id': appeal_id,
    }

    for key in VIOLATION_INFO_KEYS:
        appeal[key] = get_value(data, key)

    return appeal


async def send_success_sending(user_id: int,
                               appeal_id: int,
                               appeal: dict) -> None:
    logger.info(f'Успешно отправлено - {str(user_id)}:{str(appeal_id)}')
    state = dp.current_state(chat=user_id, user=user_id)
    language = await get_ui_lang(state)
    text = locales.text(language, 'successful_sending')
    ok_post = await bot.send_message(user_id,
                                     text,
                                     parse_mode='HTML',
                                     reply_to_message_id=appeal_id,
                                     disable_notification=True)

    await statistic.count_sent_appeal()

    async with state.proxy() as data:
        delete_files = True

        if appeal:
            await send_appeal_textfile_to_user(appeal['text'],
                                               language,
                                               user_id,
                                               appeal_id)

            delete_files = await share_violation_post(
                language,
                appeal,
                reply_id=ok_post.message_id)

        await delete_appeal_from_user_queue(data,
                                            user_id,
                                            appeal_id,
                                            delete_files)


async def share_violation_post(language: str, appeal: dict, reply_id: int):
    title = get_violation_caption(language,
                                  appeal['violation_datetime'],
                                  appeal['violation_address'],
                                  appeal['violation_vehicle_number'])

    await share_post(user_id=appeal['user_id'],
                     appeal_id=appeal['appeal_id'],
                     reply_id=reply_id,
                     reply_type=config.VIOLATION,
                     title_text=title,
                     photo_paths=appeal['violation_photo_files_paths'],
                     photo_ids=appeal['violation_photo_ids'],
                     coordinates=appeal['violation_location'])

    logger.info(f'Отправили шариться по сетям - '
                f'{str(appeal["user_id"])}:{str(appeal["appeal_id"])}')

    # files will be deleted during sharing in broadcast service
    return False


async def share_response_post(language: str,
                              violation_url: str,
                              photo_path: Optional[str],
                              photo_id: Optional[str],
                              user_id: int,
                              post_id: int,
                              reply_id: int,
                              text: str = '') -> bool:
    violation_title = locales.text(language, 'violator')

    title = f'{config.RESPONSE_HASHTAG}\n' \
        f'{violation_title} {violation_url}'

    photo_paths = [photo_path] if photo_path else []
    photo_ids = [photo_id] if photo_id else []

    await share_post(user_id,
                     post_id,
                     reply_id,
                     reply_type=config.POLICE_RESPONSE,
                     title_text=title,
                     body_text=text,
                     body_formatting=[config.ITALIC],
                     photo_paths=photo_paths,
                     photo_ids=photo_ids)

    logger.info(f'Отправили шариться по сетям ответ ГАИ - '
                f'{str(user_id)}:{str(post_id)}')

    # files will be deleted during sharing in broadcast service
    return False


async def share_post(user_id: int,
                     appeal_id: int,
                     reply_id: int,
                     reply_type: str = '',
                     title_text: str = '',
                     title_formatting: list = [],
                     body_text: str = '',
                     body_formatting: list = [],
                     photo_paths: list = [],
                     photo_ids: list = [],
                     coordinates: list = [None, None]):
    title = {
        'text': title_text,
        'formatting': title_formatting,
    }

    body = {
        'text': body_text,
        'formatting': body_formatting,
    }

    data = {
        'title': title,
        'body': body,
        'photo_paths': photo_paths,
        'tg_photo_ids': photo_ids,
        'coordinates': coordinates,
        'user_id': user_id,
        'appeal_id': appeal_id,
        'reply_id': reply_id,
        'reply_type': reply_type,
    }

    await rabbit_http.send_sharing(data)


async def add_channel_post_to_success_police_response(language: str,
                                                      user_id: int,
                                                      message_id: int,
                                                      url: str):
    text = locales.text(language, 'response_sended_full').format(url)

    await bot.edit_message_text(text,
                                user_id,
                                message_id,
                                parse_mode='HTML')


async def add_channel_post_to_success_violation(language: str,
                                                user_id: int,
                                                message_id: int,
                                                url: str):
    text0 = locales.text(language, 'successful_sending') + '\n'
    channel_name = config.CHANNEL.replace('@', 'https://t.me/')
    text1 = locales.text(language, 'police_response').format(url, channel_name)

    keyboard = types.InlineKeyboardMarkup()

    police_response_button = types.InlineKeyboardButton(
        text=locales.text(language, 'police_response_button'),
        callback_data='/police_response'+url)

    keyboard.add(police_response_button)

    await bot.edit_message_text(text0 + text1,
                                user_id,
                                message_id,
                                reply_markup=keyboard,
                                parse_mode='HTML')


async def ask_to_enter_captcha(user_id: int,
                               appeal_id: int,
                               captcha_url: str,
                               answer_queue: str) -> None:
    logger.info(f'Приглашаем заполнить капчу - {user_id}')
    state = dp.current_state(chat=user_id, user=user_id)

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        data['appeal_id'] = appeal_id
        data['appeal_response_queue'] = answer_queue

    data_to_preserve = {
        'appeal_id': appeal_id,
        'appeal_response_queue': answer_queue,
    }

    await states_stack.add(user_id, data_to_preserve)

    text = locales.text(language,
                        'invite_to_enter_captcha').format(captcha_url)

    keyboard = types.InlineKeyboardMarkup()

    cancel_button = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(cancel_button)

    await bot.send_message(user_id,
                           text,
                           parse_mode='HTML',
                           reply_markup=keyboard,
                           reply_to_message_id=appeal_id)

    await state.set_state(Form.entering_captcha.state)


async def send_appeal(user_id: int, appeal_id: int) -> None:
    logger.info(f'Шлем обращение - {user_id}')
    state = dp.current_state(chat=user_id, user=user_id)

    async with state.proxy() as data:
        delete_prepared_violation(data)
        appeal = get_appeal_from_user_queue(data, appeal_id)

        if not appeal:
            await parse_appeal_from_message(data, user_id, appeal_id)
            return

        await rabbit_http.send_appeal(appeal, user_id)

        language = await get_ui_lang(data=data)
        text = locales.text(language, 'appeal_sent')

        logger.info(f'Обращение {str(appeal_id)} ' +
                    f'поставлено в очередь - {str(user_id)}')

        await bot.send_message(user_id, text)

        # leave files on disk because we need them to share later
        await delete_appeal_from_user_queue(data,
                                            user_id,
                                            appeal_id,
                                            with_files=False)

        await Form.operational_mode.set()


async def parse_appeal_from_message(data: FSMContextProxy,
                                    user_id: int,
                                    appeal_id: int) -> None:
    appeal_photos_start_id = appeal_id - 1

    if not await fill_photos_violation_data(data,
                                            user_id,
                                            appeal_photos_start_id) or \
            not await fill_text_violation_data(data, user_id, appeal_id):
        delete_prepared_violation(data)
        language = await get_ui_lang(data=data)
        text = locales.text(language, 'appeal_resending_failed')
        await bot.send_message(user_id, text)
        return

    await ask_for_sending_approvement(user_id, data)


async def process_entered_violation(data: FSMContextProxy,
                                    user_id: int,
                                    appeal_id: int):
    await photo_manager.set_id_to_current_photos(user_id, appeal_id)
    await photo_manager.clear_storage(user_id)

    if not await get_prepared_photos(data, user_id, appeal_id):
        await photo_manager.clear_storage(user_id, appeal_id)
        return

    appeal = await compose_appeal(data, user_id, appeal_id)
    add_appeal_to_user_queue(data, appeal, appeal_id)
    delete_prepared_violation(data)


async def fill_photos_violation_data(data: FSMContextProxy,
                                     user_id: int,
                                     message_start_id: int) -> bool:
    message_id = message_start_id

    photos_message = await bot.forward_message(chat_id=config.TRASH_CHANNEL,
                                               from_chat_id=user_id,
                                               message_id=message_id,
                                               disable_notification=True)

    while photos_message.photo:
        await add_photo_to_attachments(photos_message.photo[-1],
                                       data,
                                       user_id)

        message_id -= 1

        await bot.delete_message(chat_id=config.TRASH_CHANNEL,
                                 message_id=photos_message.message_id)

        photos_message = await bot.forward_message(
            chat_id=config.TRASH_CHANNEL,
            from_chat_id=user_id,
            message_id=message_id,
            disable_notification=True)

    await bot.delete_message(chat_id=config.TRASH_CHANNEL,
                             message_id=photos_message.message_id)

    return True


async def fill_text_violation_data(data: FSMContextProxy,
                                   user_id: int,
                                   appeal_id: int) -> bool:
    language = await get_ui_lang(data=data)

    appeal_message = await bot.forward_message(chat_id=config.TRASH_CHANNEL,
                                               from_chat_id=user_id,
                                               message_id=appeal_id,
                                               disable_notification=True)

    violation_data = appeal_summary.parse_violation_data(language,
                                                         appeal_message.text)

    await bot.delete_message(chat_id=config.TRASH_CHANNEL,
                             message_id=appeal_message.message_id)

    if not violation_data:
        return False

    data['violation_vehicle_number'] = \
        violation_data['violation_vehicle_number']

    address = violation_data['violation_address']
    data['violation_datetime'] = violation_data['violation_datetime']
    data['violation_caption'] = violation_data['violation_caption']
    recipient = locales.get_region_code(violation_data['violation_recipient'])
    save_recipient(data, recipient)

    coordinates = await locator.get_coordinates(address)
    await save_violation_address(address, coordinates, data)

    return True


async def status_received(status: str) -> None:
    sender_data: dict = json.loads(status)
    queue_id = str(get_value(sender_data, 'answer_queue', 'undefined'))

    logger.info(f'Прилетел статус: ' +
                f'{str(sender_data["user_id"])} - {queue_id} - ' +
                f'{sender_data["type"]}')

    user_id = int(sender_data['user_id'])
    appeal_id = int(sender_data['appeal_id'])
    appeal = sender_data.get('appeal', dict())

    if sender_data['type'] == config.OK:
        asyncio.run_coroutine_threadsafe(
            send_success_sending(user_id, appeal_id, appeal),
            loop)
    elif sender_data['type'] == config.CAPTCHA_URL:
        asyncio.run_coroutine_threadsafe(
            ask_to_enter_captcha(user_id,
                                 appeal_id,
                                 sender_data['captcha'],
                                 sender_data['answer_queue']),
            loop
        )
    elif sender_data['type'] == config.CAPTCHA_OK:
        asyncio.run_coroutine_threadsafe(
            reply_that_captcha_ok(user_id, appeal_id),
            loop
        )
    elif sender_data['type'] == config.SENDING_CANCELLED:
        asyncio.run_coroutine_threadsafe(
            cancel_sending(user_id, appeal_id, sender_data['message']),
            loop
        )
    elif sender_data['type'] == config.BAD_EMAIL:
        asyncio.run_coroutine_threadsafe(
            tell_about_bad_email(user_id, appeal_id),
            loop
        )
    elif sender_data['type'] == config.POST_URL:
        message_id = sender_data.get('reply_id', 0)
        message_type = sender_data.get('reply_type', '')
        post_url = sender_data.get('post_url', '')

        asyncio.run_coroutine_threadsafe(
            add_url_to_message(user_id,
                               appeal_id,
                               message_id,
                               message_type,
                               post_url),
            loop
        )


async def add_url_to_message(user_id: int,
                             appeal_id: int,
                             message_id: int,
                             message_type: str,
                             post_url: str):
    state = dp.current_state(chat=user_id, user=user_id)
    language = await get_ui_lang(state)

    if message_type == config.VIOLATION:
        logger.info(f'Отправили в канал - {str(user_id)}:{str(appeal_id)}')

        await add_channel_post_to_success_violation(language,
                                                    user_id,
                                                    message_id,
                                                    post_url)
    elif message_type == config.POLICE_RESPONSE:
        await add_channel_post_to_success_police_response(language,
                                                          user_id,
                                                          message_id,
                                                          post_url)


async def tell_about_bad_email(user_id: int, appeal_id: int):
    state = dp.current_state(chat=user_id, user=user_id)
    language = await get_ui_lang(state)
    text = locales.text(language, 'bad_email')

    await bot.send_message(user_id,
                           text,
                           reply_to_message_id=appeal_id)


async def reply_that_captcha_ok(user_id: int, appeal_id: int) -> None:
    state = dp.current_state(chat=user_id, user=user_id)
    language = await get_ui_lang(state)
    text = locales.text(language, 'captcha_ok')

    await bot.send_message(user_id,
                           text,
                           reply_to_message_id=appeal_id,
                           disable_notification=True)


async def get_appeal_email(data, user_id) -> Optional[str]:
    password = get_value(data, 'sender_email_password', '')

    if not password:
        return None

    email = get_value(data, 'sender_email', '')

    if await Email(loop).check_connection(email, password):
        return email

    language = await get_ui_lang(data=data)
    text = locales.text(language, "email_unavailable").format(email)

    await bot.send_message(user_id,
                           text,
                           disable_notification=True,
                           parse_mode='HTML')
    return None


async def send_captcha_text(state: FSMContext,
                            user_id: int,
                            captcha_text: str,
                            appeal_id: int) -> None:
    logger.info(f'Посылаем текст капчи - {user_id}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        appeal_email = await get_appeal_email(data, user_id)

    try:
        await rabbit_http.send_captcha_text(
            captcha_text,
            user_id,
            appeal_id,
            appeal_email,
            get_value(data, 'appeal_response_queue'))

    except Exception as exc:
        text = locales.text(language, 'sending_failed') + '\n' + str(exc)
        logger.error('Неудачка - ' + str(user_id) + '\n' + str(exc))
        await bot.send_message(user_id, text)


def ensure_attachments_availability(data: FSMContextProxy):
    if (('violation_attachments' not in data) or
            ('violation_photo_ids' not in data) or
            ('violation_photo_files_paths' not in data) or
            ('violation_photos_amount' not in data)):
        data['violation_attachments'] = []
        data['violation_photo_ids'] = []
        data['violation_photo_files_paths'] = []
        data['violation_photos_amount'] = 0


async def violation_storage_full(state):
    # потанцевально узкое место, все потоки всех пользователей будут ждать
    # пока кто-то один проверяет, если я правильно понимаю
    # нужно сделать каждому пользователю свой личный семафорчик, но я пока
    # что не знаю как
    async with semaphore, state.proxy() as data:
        ensure_attachments_availability(data)

        violation_photos_amount = get_value(data, 'violation_photos_amount')

        if violation_photos_amount < config.MAX_VIOLATION_PHOTOS:
            data['violation_photos_amount'] += 1
            return False
        else:
            return True


async def add_photo_to_attachments(photo: PhotoSize,
                                   data: FSMContextProxy,
                                   user_id: int) -> None:
    ensure_attachments_availability(data)
    data['violation_photo_ids'].append(photo['file_id'])
    photo_manager.stash_photo(user_id, photo)


async def get_prepared_photos(data: FSMContextProxy,
                              user_id: int,
                              appeal_id: int) -> bool:
    photos_data = await photo_manager.get_photo_data(user_id, appeal_id)

    if not photo_manager.valid(photos_data):
        return False

    for image_url in photos_data['urls']:
        data['violation_attachments'].append(image_url)

    for image_path in photos_data['file_paths']:
        data['violation_photo_files_paths'].append(image_path)

    page_url = photos_data['page_url']
    data['violation_photo_page'] = page_url

    logger.info('Вгрузили фоточки - ' + str(user_id))
    return True


def delete_prepared_violation(data: FSMContextProxy) -> None:
    for key in VIOLATION_INFO_KEYS:
        pop_value(data, key)

    pop_value(data, 'appeal_response_queue')


def save_entered_address(data: FSMContextProxy, address: str):
    addresses = get_value(data, 'previous_violation_addresses')

    if address not in addresses:
        addresses.reverse()
        addresses.append(address)
        addresses.reverse()
    else:  # move element to first position
        addresses.insert(0, addresses.pop(addresses.index(address)))

    while len(addresses) > config.ADDRESS_AMOUNT_TO_SAVE:
        addresses.pop()

    data['previous_violation_addresses'] = addresses


def delete_saved_address(data: FSMContextProxy, address: str):
    addresses = get_value(data, 'previous_violation_addresses')

    if address in addresses:
        addresses.pop(addresses.index(address))


def set_default(data: Union[FSMContextProxy, dict],
                key: str,
                force=False) -> None:
    if (key not in data) or force:
        data[key] = get_default_value(key)


def get_default_value(key):
    default_values = {
        'verified': False,
        'letter_lang': config.RU,
        'ui_lang': config.BY,
        'recipient': config.MINSK,
        'violation_attachments': [],
        'appeals': {},
        'violation_photo_ids': [],
        'violation_photo_files_paths': [],
        'violation_photos_amount': 0,
        'violation_location': [],
        'states_stack': [],
        'violation_date': datetime_parser.get_current_datetime_str(),
        'previous_violation_addresses': [],
        'appeal_id': 0,
        'message_to_reply': None,
    }

    try:
        return default_values[key]
    except KeyError:
        return ''


def add_appeal_to_user_queue(data: FSMContextProxy,
                             appeal: dict,
                             appeal_id: int) -> None:
    appeals = get_value(data, 'appeals')
    delete_old_appeals(appeals)

    if not get_value(appeals, str(appeal_id), {}, read_only=True):
        logger.info(f'Такого обращения еще нет в хранилище - {appeal_id}')
        appeals[str(appeal_id)] = appeal
        data['appeals'] = appeals


def get_original_appeal_id(message: types.Message,
                           it_is_reply=False) -> Tuple[bool, int]:
    if message.reply_to_message:
        logger.info(f'Это реплай - {str(message.from_user.id)}')
        return get_original_appeal_id(message.reply_to_message, True)
    else:
        return it_is_reply, message.message_id


def get_appeal_from_user_queue(data: FSMContextProxy,
                               appeal_id: int) -> dict:
    appeals = get_value(data, 'appeals')
    appeal = get_value(appeals, str(appeal_id), {}, read_only=True)
    return appeal


async def delete_appeal_from_user_queue(data: FSMContextProxy,
                                        user_id: int,
                                        appeal_id: int,
                                        with_files=True) -> None:
    appeals: dict = get_value(data, 'appeals')
    appeals.pop(str(appeal_id), 'default_value')
    data['appeals'] = appeals

    # clear photos storage except files on disk
    await photo_manager.clear_storage(user_id, appeal_id, with_files)


def delete_old_appeals(appeals: dict,
                       limit: int = config.APPEAL_STORAGE_LIMIT) -> dict:
    keys = list(appeals.keys())
    keys.sort(reverse=True)
    keys_amount = len(keys)
    logger.info(f'Длина хранилища обращений - {keys_amount}')

    if keys_amount > limit:
        keys_to_delete = keys[limit:]

        for key in keys_to_delete:
            appeals.pop(key)

    return appeals


async def pop_saved_state(user_id: int, from_id: int):
    message_id, message_text = await states_stack.pop(user_id)

    if message_id:
        await safe_forward(chat_id=user_id,
                           from_chat_id=from_id,
                           message_id=message_id)
        return

    if message_text:
        await bot.send_message(user_id, message_text)
    else:
        state = dp.current_state(chat=user_id, user=user_id)
        language = await get_ui_lang(state)
        await send_form_message(await state.get_state(),
                                user_id,
                                language)


async def safe_forward(chat_id: int,
                       from_chat_id: int,
                       message_id: int) -> None:
    try:
        await bot.forward_message(chat_id=chat_id,
                                  from_chat_id=from_chat_id,
                                  message_id=message_id)
    except Exception:
        pass


async def check_validity(pattern, message, language):
    error_message = validator.valid(message.text, *pattern)

    if error_message:
        await message.reply(locales.text(language, error_message))
        return False
    else:
        return True


def get_photos_links(data):
    text = ''

    for photo_url in get_value(data, 'violation_attachments'):
        text += f'''{photo_url}
'''

    return text.strip()


def get_appeal_text(data: Union[FSMContextProxy, dict],
                    user_id: int,
                    appeal_id: int) -> str:
    violation_data = {
        'photos': get_photos_links(data),
        'photos_post_url': get_value(data, 'violation_photo_page'),
        'vehicle_number': get_value(data, 'violation_vehicle_number'),
        'address': get_value(data, 'violation_address'),
        'datetime': get_value(data, 'violation_datetime'),
        'remark': get_value(data, 'violation_caption'),
        'sender_name': get_sender_full_name(data),
        'sender_email': get_value(data, 'sender_email'),
        'sender_phone': get_value(data, 'sender_phone'),
        'appeal_number': f'{str(user_id)}-{str(appeal_id)}',
        'appeal_datetime': datetime_parser.get_current_datetime().strftime(
            "%d-%m-%Y %H:%M"),
    }

    return AppealText.get(get_value(data, 'letter_lang'), violation_data)


async def ask_for_sending_approvement(user_id: int,
                                      data: FSMContextProxy) -> int:
    await Form.sending_approvement.set()
    language = await get_ui_lang(data=data)

    caption_button_text = locales.text(language, 'add_caption_button')

    text = await appeal_summary.compose_summary(language, data)

    await send_photos_group_with_caption(
        get_value(data, 'violation_photo_ids'),
        user_id)

    if get_value(data, 'violation_caption'):
        caption_button_text = locales.text(language,
                                           'change_caption_button')

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    approve_sending_button = types.InlineKeyboardButton(
        text=locales.text(language, 'approve_sending_button'),
        callback_data='/approve_sending')

    cancel_button = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    enter_violation_info_button = types.InlineKeyboardButton(
        text=locales.text(language, 'violation_info_button'),
        callback_data='/enter_violation_info')

    add_caption_button = types.InlineKeyboardButton(
        text=caption_button_text,
        callback_data='/add_caption')

    keyboard.add(enter_violation_info_button, add_caption_button)
    keyboard.add(approve_sending_button, cancel_button)

    message = await bot.send_message(user_id,
                                     text,
                                     reply_markup=keyboard,
                                     parse_mode='HTML',
                                     disable_web_page_preview=True)

    violation_summary = get_violation_caption(
        language,
        data['violation_datetime'],
        data['violation_address'],
        data['violation_vehicle_number']
    )

    photo_manager.stash_page(user_id, violation_summary)
    return message.message_id


def get_str_current_time():
    tz_minsk = tz.gettz('Europe/Minsk')
    current_time = datetime.now(tz_minsk)

    day = str(current_time.day).rjust(2, '0')
    month = str(current_time.month).rjust(2, '0')
    year = str(current_time.year)
    hour = str(current_time.hour).rjust(2, '0')
    minute = str(current_time.minute).rjust(2, '0')

    return f'{day}.{month}.{year} {hour}:{minute}'


async def invalid_credentials(state):
    async with state.proxy() as data:
        for user_info in REQUIRED_CREDENTIALS:
            if (user_info not in data) or (data[user_info] == ''):
                return True

    return False


async def verified_email(state):
    async with state.proxy() as data:
        return get_value(data, 'verified')


def already_entered(entered_number: str, current_enter: str) -> bool:
    entered_number = entered_number.replace(' ', '')
    entered_number = entered_number.replace('-', '')
    current_enter = current_enter.replace(' ', '')
    current_enter = current_enter.replace('-', '')

    return entered_number in current_enter


async def get_cancel_keyboard(
    data: FSMContextProxy,
    keyboard: types.InlineKeyboardMarkup = None) \
        -> types.InlineKeyboardMarkup:
    language = await get_ui_lang(data=data)

    if not keyboard:
        keyboard = types.InlineKeyboardMarkup()

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(cancel)

    return keyboard


def get_saved_adresses_keyboard(
        items: list) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    buttons = []

    for number, _ in enumerate(items):
        buttons.append(
            types.InlineKeyboardButton(
                text=f'{number+1}',
                callback_data=f'{config.PREVIOUS_ADDRESS_PREFIX}{number}')
        )

    keyboard.add(*buttons)
    return keyboard


async def get_numberplates_keyboard(
        data: FSMContextProxy,
        numberplates: List[str]) -> types.InlineKeyboardMarkup:
    language = await get_ui_lang(data=data)

    keyboard = types.InlineKeyboardMarkup()
    current_numberplates = get_value(data, 'violation_vehicle_number', '')

    for numberplate in numberplates:
        text = numberplate

        if numberplate in current_numberplates:
            text += ' ✅'

        button = types.InlineKeyboardButton(
            text=text,
            callback_data=f'/numberplate{numberplate}')

        keyboard.add(button)

    all_selected = types.InlineKeyboardButton(
        text=locales.text(language, 'all_selected_button'),
        callback_data='/all_selected')

    keyboard.add(all_selected)

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(cancel)

    return keyboard


async def get_sender_param_keyboard(language):
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    backward = types.InlineKeyboardButton(
        text=locales.text(language, 'back_button'),
        callback_data='/back_button')

    forward = types.InlineKeyboardButton(
        text=locales.text(language, 'forward_button'),
        callback_data='/forward_button')

    finish = types.InlineKeyboardButton(
        text=locales.text(language, 'finish_button'),
        callback_data='/finish_button')

    keyboard.add(backward, forward, finish)

    return keyboard


async def ask_for_sender_info(message: types.Message,
                              state: FSMContext,
                              next_state: str,
                              edit=False) -> None:
    storage_key = next_state.replace('Form:', '')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

        current_value = get_value(data,
                                  storage_key,
                                  locales.text(language, 'empty_input'))

    remark = get_remark(next_state, language)

    text = locales.text(language, next_state) + '\n' +\
        remark +\
        '\n' +\
        locales.text(language, 'current_value') + f'<b>{current_value}</b>' +\
        '\n' +\
        locales.text(language, f'{next_state}_example')

    keyboard = await get_sender_param_keyboard(language)

    if edit:
        try:
            await bot.edit_message_text(text,
                                        message.chat.id,
                                        message.message_id,
                                        reply_markup=keyboard,
                                        parse_mode='HTML')
        except MessageNotModified:
            pass
    else:
        await bot.send_message(message.chat.id,
                               text,
                               reply_markup=keyboard,
                               parse_mode='HTML')

    await state.set_state(next_state)


def get_remark(form: str, language: str) -> str:
    text_key = get_value(ADDITIONAL_MESSAGE, form, "", read_only=True)
    text = ""

    if text_key:
        text = '\n' + locales.text(language, text_key) + '\n'

    return text


async def show_private_info_summary(chat_id, state):
    language = await get_ui_lang(state)

    if await invalid_credentials(state):
        text = locales.text(language, 'no_info_warning')
        keyboard = types.InlineKeyboardMarkup()

        personal_info_button = types.InlineKeyboardButton(
            text=locales.text(language, 'send_personal_info'),
            callback_data='/enter_personal_info')

        keyboard.add(personal_info_button)
        await bot.send_message(chat_id, text, reply_markup=keyboard)
    elif not await verified_email(state):
        async with state.proxy() as data:
            await invite_to_confirm_email(data, chat_id)
    else:
        text = locales.text(language, 'ready_to_report')
        await bot.send_message(chat_id,
                               text,
                               parse_mode='HTML',
                               disable_web_page_preview=True)

    await Form.operational_mode.set()


async def message_about_short_address(chat_id: int, data: FSMContextProxy):
    language = await get_ui_lang(data=data)

    text = locales.text(language, 'short_address') + '\n' +\
        '\n' +\
        locales.text(language,
                     f'{Form.violation_address.state}_example')

    await bot.send_message(chat_id, text, parse_mode='HTML')


async def ask_for_violation_address(chat_id: int, data: FSMContextProxy):
    language = await get_ui_lang(data=data)

    text = locales.text(language, Form.violation_address.state) + '\n' +\
        locales.text(language, 'bot_can_guess_address') + '\n' +\
        '\n' +\
        locales.text(language, 'irrelevant_information_warning') + '\n' +\
        '\n' +\
        locales.text(language,
                     f'{Form.violation_address.state}_example') + '\n' +\
        '\n'

    keyboard = await get_cancel_keyboard(data)

    if get_value(data, 'previous_violation_addresses'):
        saved_adresses: list = get_value(data, 'previous_violation_addresses')
        saved_adresses_text = get_saved_addresses_list(saved_adresses)

        text += locales.text(language, 'previous_violation_addresses') + \
            '\n' + \
            '\n' + \
            saved_adresses_text

        keyboard = get_saved_adresses_keyboard(saved_adresses)
        keyboard = await get_cancel_keyboard(data, keyboard)

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.violation_address.set()


def get_saved_addresses_list(addresses: list) -> str:
    addresses_list = ''

    for number, address in enumerate(addresses):
        addresses_list += f'{number + 1}. {address}\n'

    return addresses_list


async def send_language_info(user_id: int, data: FSMContextProxy) -> None:
    text, keyboard = await get_language_text_and_keyboard(data)

    await bot.send_message(user_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def send_appeal_email_info(user_id: int, data: FSMContextProxy) -> None:
    language = await get_ui_lang(data=data)
    email = get_value(data, 'sender_email')
    text = locales.text(language, 'email_password').format(email)

    keyboard = types.InlineKeyboardMarkup(row_width=3)

    personal_info_button = types.InlineKeyboardButton(
        text=locales.text(language, 'personal_info'),
        callback_data='/personal_info')

    enter_password_button = types.InlineKeyboardButton(
        text=locales.text(language, 'enter_password'),
        callback_data='/enter_password')

    delete_password_button = types.InlineKeyboardButton(
        text=locales.text(language, 'delete_email_password'),
        callback_data='/delete_password')

    keyboard.add(personal_info_button,
                 enter_password_button,
                 delete_password_button)

    await bot.send_message(user_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


def save_recipient(data: FSMContextProxy, recipient: Optional[str]) -> None:
    if recipient is None:
        data['recipient'] = config.MINSK
    else:
        data['recipient'] = recipient


async def print_violation_address_info(state: FSMContext,
                                       user_id: int) -> None:
    async with state.proxy() as data:
        address = get_value(data, 'violation_address')
        region = get_value(data, 'recipient')
        language = await get_ui_lang(data=data)

    text = locales.text(language, 'recipient') +\
        ' <b>{}</b>.'.format(locales.text(language, region)) + '\n' +\
        '\n' +\
        locales.text(language, 'violation_address') + \
        ' <b>{}</b>'.format(address)

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_violation_addr_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_violation_addr_button'),
        callback_data='/enter_violation_addr')

    enter_recipient_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_recipient'),
        callback_data='/enter_recipient')

    keyboard.add(enter_violation_addr_button, enter_recipient_button)

    await bot.send_message(user_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def save_violation_address(address: str,
                                 coordinates: Optional[List[float]],
                                 data: FSMContextProxy):
    data['violation_address'] = address
    data['violation_location'] = coordinates

    # в этом месте сохраним адрес нарушения для использования в
    # следующем обращении
    save_entered_address(data, address)


async def ask_for_violation_time(user_id: int, language: str):
    text, keyboard = compose_violation_time_asking(
        language,
        datetime_parser.get_current_datetime_str())

    await bot.send_message(user_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.violation_datetime.set()


def get_broadcast_invitation(language: str, receiver_id: str) -> str:
    text = locales.text(language, 'send_message_to_broadcast')
    pre_receiver_text = locales.text(language, 'receiver')
    receiver_text = locales.text(language, receiver_id)
    return text + f'\n\n{pre_receiver_text}: {receiver_text}'


def get_broadcast_keyboard(language: str,
                           receiver_id: str) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()

    mode_button = types.InlineKeyboardButton(
        text=locales.text(language, 'receiver'),
        callback_data=f'/change_receiver {receiver_id}')

    cancel_button = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(mode_button, cancel_button)
    return keyboard


def get_violation_datetime_keyboard(
        language: str) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    yesterday_button = types.InlineKeyboardButton(
        text=locales.text(language, 'yesterday_button'),
        callback_data='/yesterday')

    before_yesterday_button = types.InlineKeyboardButton(
        text=locales.text(language, 'before_yesterday_button'),
        callback_data='/before_yesterday')

    current_time_button = types.InlineKeyboardButton(
        text=locales.text(language, 'current_time_button'),
        callback_data='/current_time')

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(before_yesterday_button,
                 yesterday_button,
                 current_time_button,
                 cancel)

    return keyboard


async def send_photos_group_with_caption(photos_id: list,
                                         chat_name: Union[str, int],
                                         caption='') -> str:
    photos = []

    for count, photo_id in enumerate(photos_id):
        text = ''

        # первой фотке добавим общее описание
        if count == 0:
            text = caption

        photo = PhotoItem('photo', photo_id, text)
        photos.append(photo)

    message = await bot.send_media_group(chat_id=chat_name, media=photos)
    return get_channel_post_url_by_id(message[0].message_id)


def get_channel_post_url_by_id(post_id: int) -> str:
    channel = config.CHANNEL.replace('@', '')
    return f't.me/{channel}/{str(post_id)}'


def prepare_registration_number(number: str):
    """replace all cyrillyc to latin"""

    kyrillic = 'АВСЕНКМОРТХУІ'
    latin = 'ABCEHKMOPTXYI'

    up_number = number.upper().strip()

    for num, symbol in enumerate(kyrillic):
        up_number = up_number.replace(symbol, latin[num])

    return up_number


def get_photo_step_keyboard(language: str) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    violation_info_button = types.InlineKeyboardButton(
        text=locales.text(language, 'violation_info_button'),
        callback_data='/enter_violation_info')

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(violation_info_button, cancel)
    return keyboard


async def ask_about_short_address(state: FSMContext, chat_id: int) -> None:
    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        user_city = get_value(data, 'sender_city')

    question = locales.text(language, 'no_city_in_address')

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    confirm_button = types.InlineKeyboardButton(
        text=locales.text(language, 'address_is_full'),
        callback_data='/confirm_button')

    if user_city:
        press_button_text = " " + locales.text(language, 'or_press_button')
        city_button_text = user_city
    else:
        press_button_text = ''
        city_button_text = ''

    city_button = types.InlineKeyboardButton(
        text=city_button_text,
        callback_data='/user_city_as_violations')

    keyboard.add(city_button, confirm_button)

    input_invitation = \
        locales.text(language,
                     'input_violation_city').format(press_button_text)

    text = question + "\n\n" + input_invitation

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.no_city_in_address.set()


async def set_violation_address(chat_id: int,
                                address: str,
                                state: FSMContext) -> None:
    coordinates = await locator.get_coordinates(address)
    recipient = await locator.get_region(coordinates)

    async with state.proxy() as data:
        await save_violation_address(address, coordinates, data)
        save_recipient(data, recipient)


def add_numberplate_to_user_data(data: FSMContextProxy,
                                 numberplate: str) -> FSMContextProxy:
    def remove_prefix(text, prefix):
        if text.startswith(prefix):
            return text[len(prefix):]

        return text

    data['violation_vehicle_number'] += f', {numberplate}'

    data['violation_vehicle_number'] = remove_prefix(
        data['violation_vehicle_number'],
        ', '
    )

    return data


def delete_numberplate_from_user_data(data: FSMContextProxy,
                                      numberplate: str) -> FSMContextProxy:
    numberplates: str = data['violation_vehicle_number']
    numberplates = numberplates.replace(f', {numberplate}', '')
    numberplates = numberplates.replace(f'{numberplate}, ', '')
    numberplates = numberplates.replace(numberplate, '')
    data['violation_vehicle_number'] = numberplates
    return data


def maybe_no_city_in_address(address: str) -> bool:
    address = address.lower()
    locality_indicators = ['аг.', 'г.', 'в.']

    for indicator in locality_indicators:
        if indicator in address:
            return False

    unneeded = ['вул.', 'зав.', 'пер.', 'д.', 'ул.', 'пр.', 'пр-т.', 'пр-т']

    for word in unneeded:
        address = case_insensitive_delete(address, word)

    cities_by = ['мінск', 'брэст', 'гродна', 'віцебск', 'гомель', 'магілёў']
    cities_ru = ['минск', 'брест', 'гродно', 'витебск', 'гомель', 'могилев']

    for city in cities_by + cities_ru:
        if city in address:
            return False

    comma_parts_len = len(address.split(','))

    if comma_parts_len >= 3:
        return False

    if comma_parts_len > 1 and comma_parts_len < 3:
        return True

    space_parts_len = len(address.replace(',', '').split(' '))

    if space_parts_len >= 4:
        return False

    if space_parts_len > 1 and space_parts_len < 4:
        return True

    return False


def case_insensitive_delete(text: str, to_delete: str) -> str:
    insensitive_hippo = re.compile(re.escape(to_delete), re.IGNORECASE)
    return insensitive_hippo.sub('', text)


def compose_violation_time_asking(
        language: str,
        datetime_iso: str) -> Tuple[str, types.InlineKeyboardMarkup]:
    day, month, year = datetime_parser.parse_datetime(datetime_iso)
    current_time = get_str_current_time()

    text = locales.text(
        language, 'enter_time_in_yesterday').format(
            f'{day.rjust(2, "0")}.' +
            f'{month.rjust(2, "0")}.' +
            f'{year.rjust(2, "0")}') + '\n' +\
        '\n' +\
        locales.text(language, 'example') + \
        ' <b>{}</b>.'.format(current_time)

    keyboard = get_violation_datetime_keyboard(language)

    return text, keyboard


async def react_to_time_button(user_id: int,
                               message_id: int,
                               state: FSMContext,
                               day_to_shift: int = 0) -> None:
    async with state.proxy() as data:
        data['violation_date'] = violation_date = \
            datetime_parser.get_current_datetime_str(day_to_shift)

        language = await get_ui_lang(data=data)

    text, keyboard = compose_violation_time_asking(language,
                                                   violation_date)
    try:
        await bot.edit_message_text(text,
                                    user_id,
                                    message_id,
                                    reply_markup=keyboard,
                                    parse_mode='HTML')
    except MessageNotModified:
        pass


async def send_form_message(form: Optional[str],
                            user_id: int,
                            language: str) -> None:
    text = locales.text(language, 'continue_work') + '\n\n' + \
        locales.text(language, form)

    await bot.send_message(user_id, text)


async def share_to_social_networks(message: types.Message,
                                   post_type: str):
    text, photo_paths, photo_ids = await get_social_data_from_post(message,
                                                                   post_type)

    await share_post(user_id=message.chat.id,
                     appeal_id=message.message_id,
                     reply_id=message.message_id,
                     body_text=text,
                     photo_paths=photo_paths,
                     photo_ids=photo_ids)


async def get_social_data_from_post(
        message: types.Message,
        post_type: str) -> Tuple[str, List[str], List[str]]:
    text = message.text or message.caption
    photo_pathes = list()
    photo_ids = list()

    if post_type == str(types.ContentType.PHOTO):
        photo_id = message.photo[-1]['file_id']
        photo_path = await photo_manager.store_photo(message.chat.id,
                                                     message.photo[-1],
                                                     message.message_id)

        photo_ids.append(photo_id)
        photo_pathes.append(photo_path)

    return text, photo_pathes, photo_ids


async def share_to_users(message: types.Message):
    async for user_id in users.every_id():
        try:
            await message.send_copy(user_id, disable_notification=True)
        except CantTalkWithBots:
            pass
        except Exception:
            logger.exception("Ошибка при отправке всем пользователям")


async def show_settings(message: types.Message, state: FSMContext):
    logger.info('Настройки - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        email = get_value(data, 'sender_email')

        saved_violation_addresses = get_value(data,
                                              'previous_violation_addresses')

    text = locales.text(language, 'select_section')

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    personal_info_button = types.InlineKeyboardButton(
        text=locales.text(language, 'personal_info'),
        callback_data='/personal_info')

    appeal_email_button = types.InlineKeyboardButton(
        text=locales.text(language, 'appeal_email'),
        callback_data='/appeal_email')

    language_settings_button = types.InlineKeyboardButton(
        text=locales.text(language, 'language_settings'),
        callback_data='/language_settings')

    clear_saved_violation_addresses_button = types.InlineKeyboardButton(
        text=locales.text(language, 'clear_saved_violation_addresses'),
        callback_data='/clear_saved_violation_addresses')

    keyboard.add(personal_info_button, language_settings_button)

    if email:
        keyboard.add(appeal_email_button)

    if saved_violation_addresses:
        keyboard.add(clear_saved_violation_addresses_button)

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


def get_next_item(items: list, current: Any) -> Any:
    return_next = False

    while True:
        for item in items:
            if return_next:
                return item

            if item == current:
                return_next = True


def get_input_name_invite_text(language, name, invitation, example):
    text = locales.text(language, invitation) + '\n' +\
        '\n' +\
        locales.text(language, 'current_value') + f'<b>{name}</b>' +\
        '\n' +\
        locales.text(language, example)

    return text


async def get_statistic() -> dict:
    total_users_count = await statistic.get_total_users_count()
    registered_users_count = await statistic.get_registered_users_count()
    appeals_sent = await statistic.get_appeals_sent_count()
    appeals_sent_today = await statistic.get_appeals_sent_today_count()
    appeals_sent_yesterday = await statistic.get_appeals_sent_yesterday_count()
    appeals_queue_size = await statistic.get_appeal_queue_size()

    return {
        'total_users': str(total_users_count),
        'registered_users': str(registered_users_count),
        'appeals_sent': str(appeals_sent),
        'appeals_sent_today': str(appeals_sent_today),
        'appeals_sent_yesterday': str(appeals_sent_yesterday),
        'appeal_queue_size': str(appeals_queue_size),
    }


def post_from_channel(message: types.Message) -> bool:
    if not message.forward_from_chat:
        return False

    return message.forward_from_chat.mention == config.CHANNEL


def message_is_violation_post(message: types.Message) -> bool:
    samples = []

    for language in config.LANGUAGES:
        samples.append(locales.text(language, 'violation_datetime'))

    try:
        if message.html_text:
            for sample in samples:
                if sample in message.html_text:
                    return True
    except TypeError:
        pass

    return False


async def police_response_sending(message: types.Message, state: FSMContext):
    if not message_is_violation_post(message):
        return

    url = get_channel_post_url_by_id(message.forward_from_message_id)
    await ask_for_police_response(state, message.from_user.id, url)


async def ask_for_police_response(state: FSMContext,
                                  user_id: int,
                                  violation_post_url: str):
    logger.info(f'Просим прислать ответГАИ - {str(user_id)}')

    async with state.proxy() as data:
        data['responsed_post_url'] = violation_post_url
        language = await get_ui_lang(data=data)
        keyboard = await get_cancel_keyboard(data)

    text = locales.text(language, Form.police_response.state)
    await bot.send_message(user_id, text, reply_markup=keyboard)
    await Form.police_response.set()
    await schedule_auto_cancel(user_id, state)


async def schedule_auto_cancel(user_id: int, state: FSMContext):
    await schedule_auto_back(user_id,
                             str(await state.get_state()),
                             str(Form.operational_mode.state))


async def schedule_auto_back(user_id: int,
                             current_state: str,
                             state_to_back: str):
    task_to_cancel = {
        'user_id': user_id,
        'executor': CANCEL_ON_IDLE,
        'kvargs': {
            'expected_state': current_state,
            'state_to_set': state_to_back,
            'user_id': user_id,
        },
        'execute_time': datetime_parser.get_current_datetime_str(
            shift_hours=config.DEFAULT_SCHEDULER_PAUSE)
    }

    await scheduler.add_task(task_to_cancel)


def too_early_police_button(message_date: datetime) -> bool:
    MINIMUM_AGE = timedelta(days=2)
    now = datetime.now()

    return now - message_date < MINIMUM_AGE


async def tell_that_too_early(user_id: int, language: str):
    text = locales.text(language, "too_early_for_police_responce").format(
        config.RESPONSE_EXAMPLE
    )

    await bot.send_message(user_id,
                           text,
                           parse_mode='HTML')


async def show_personal_info(message: types.Message, state: FSMContext):
    logger.info('Показ инфы отправителя - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        empty_input = locales.text(language, 'empty_input')

        full_name = get_sender_full_name(data) or empty_input
        email = get_value(data, 'sender_email', empty_input)
        phone = get_value(data, 'sender_phone', empty_input)
        address = get_sender_address(data) or empty_input

        text = locales.text(language, 'personal_data') + '\n' + '\n' +\
            locales.text(language, 'sender_name') + f' <b>{full_name}</b>' +\
            '\n' +\
            locales.text(language, 'sender_email') + f' <b>{email}</b>' +\
            '\n' +\
            locales.text(language, 'sender_phone') + f' <b>{phone}</b>' +\
            '\n' +\
            locales.text(language, 'sender_address') + f' <b>{address}</b>'

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_personal_info_button = types.InlineKeyboardButton(
        text=locales.text(language, 'enter_personal_info_button'),
        callback_data='/enter_personal_info')

    delete_personal_info_button = types.InlineKeyboardButton(
        text=locales.text(language, 'delete_personal_info_button'),
        callback_data='/reset')

    keyboard.add(enter_personal_info_button, delete_personal_info_button)

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def get_language_text_and_keyboard(
        data: FSMContextProxy) -> Tuple[str, types.InlineKeyboardMarkup]:
    language = await get_ui_lang(data=data)

    ui_lang_name = locales.text(language, 'lang' + language)
    letter_lang_name = locales.text(language,
                                    'lang' + get_value(data, 'letter_lang'))

    text = locales.text(language, 'current_ui_lang') +\
        ' <b>{}</b>.'.format(ui_lang_name) + '\n' +\
        '\n' +\
        locales.text(language, 'current_letter_lang') +\
        ' <b>{}</b>.'.format(letter_lang_name)

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    change_ui_language_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_ui_language_button'),
        callback_data='/change_ui_language')

    change_letter_language_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_letter_language_button'),
        callback_data='/change_letter_language')

    keyboard.add(change_ui_language_button, change_letter_language_button)

    return text, keyboard


async def ask_for_numberplate(user_id: int,
                              data: FSMContextProxy,
                              message_id: Optional[int] = None):
    """
    Send bot invitation to enter numberplate
    """
    await Form.vehicle_number.set()

    if initial_asking_for_numberplate(message_id):
        data['violation_vehicle_number'] = ''

    recognized_numberplates, message_id = \
        await get_recognized_numberplates(data, user_id, message_id)

    if recognized_numberplates:
        await ask_to_choose_numberplates(user_id,
                                         data,
                                         recognized_numberplates,
                                         message_id)
    else:
        await ask_to_enter_numberplates(user_id, data, message_id)


async def get_recognized_numberplates(
        data: FSMContextProxy,
        user_id: int,
        message_id: Optional[int]) -> Tuple[List[str], Optional[int]]:
    counter = 0
    language = await get_ui_lang(data=data)

    while await photo_manager.numberplate_tasks_in_progress(user_id):
        counter += 1

        message_id = await show_magic_message(user_id,
                                              message_id,
                                              language,
                                              counter)
        await asyncio.sleep(2)

    recognized_numberplates = await photo_manager.get_numberplates(user_id)

    return recognized_numberplates, message_id


async def show_magic_message(user_id: int,
                             message_id: Optional[int],
                             language: str,
                             counter: int) -> int:
    text = locales.text(language, 'magical_recognition').format('🦄' * counter)
    keyboard = types.InlineKeyboardMarkup()

    button = types.InlineKeyboardButton(
        text=locales.text(language, 'stop_magic_button'),
        callback_data=f'/stop_recognition_magic')

    keyboard.add(button)

    if message_id:
        message = await bot.edit_message_text(text,
                                              user_id,
                                              message_id,
                                              reply_markup=keyboard,
                                              parse_mode='HTML')
    else:
        message = await bot.send_message(user_id,
                                         text,
                                         reply_markup=keyboard,
                                         parse_mode='HTML')

    return message.message_id


def initial_asking_for_numberplate(existed_message_id: Optional[int]) -> bool:
    return not existed_message_id


def address_too_short(address_line: str) -> bool:
    return len(address_line) <= config.MIN_ADDRESS_LENGTH


def get_previos_address_number(text: str) -> Optional[int]:
    try:
        number = int(text) - 1
    except ValueError:
        return None

    if number >= 0 and number < config.ADDRESS_AMOUNT_TO_SAVE:
        return number

    return None


async def use_saved_address(address_index: int,
                            message: types.Message,
                            state: FSMContext):
    async with state.proxy() as data:
        addresses = get_value(data, 'previous_violation_addresses')

        try:
            previous_address = addresses[int(address_index)]
        except KeyError:
            logger.error('Ошибка при вводе предыдущего адреса' +
                         f'{str(message.from_user.id)}.\n' +
                         f'Адреса: {addresses}\n' +
                         f'Индекс: {address_index}')

            previous_address = message.text

    logger.info(f'Выбрался адрес: {previous_address} - ' +
                f'{str(message.from_user.id)}:' +
                f'{message.from_user.username}')

    await set_violation_address(message.chat.id, previous_address, state)

    if maybe_no_city_in_address(previous_address):
        logger.info(
            f'Адрес без города: {previous_address} - ' +
            f'{str(message.from_user.id)}:' +
            f'{message.from_user.username}')

        await ask_about_short_address(state, message.chat.id)
    else:
        await print_violation_address_info(state, message.chat.id)
        language = await get_ui_lang(state)
        await ask_for_violation_time(message.chat.id, language)


async def ask_to_choose_numberplates(user_id: int,
                                     data: FSMContextProxy,
                                     numberplates: List[str],
                                     message_id: Optional[int]):
    language = await get_ui_lang(data=data)

    button_name = locales.text(language, 'all_selected_button')

    invitation_text = locales.text(
        language,
        f'{Form.vehicle_number.state}_choose'
    ).format(button_name)

    text = \
        invitation_text + '\n' +\
        '\n' +\
        locales.text(language, f'{Form.vehicle_number.state}_example')

    keyboard = await get_numberplates_keyboard(data, numberplates)

    if message_id:
        await bot.edit_message_text(text,
                                    user_id,
                                    message_id,
                                    reply_markup=keyboard,
                                    parse_mode='HTML')
    else:
        await bot.send_message(user_id,
                               text,
                               reply_markup=keyboard,
                               parse_mode='HTML')


async def ask_to_enter_numberplates(user_id: int,
                                    data: FSMContextProxy,
                                    message_id: int = None):
    language = await get_ui_lang(data=data)

    text = locales.text(language, Form.vehicle_number.state) + '\n' +\
        '\n' +\
        locales.text(language, f'{Form.vehicle_number.state}_example')

    keyboard = await get_cancel_keyboard(data)

    if message_id:
        await bot.edit_message_text(text,
                                    user_id,
                                    message_id,
                                    reply_markup=keyboard,
                                    parse_mode='HTML')
    else:
        await bot.send_message(user_id,
                               text,
                               reply_markup=keyboard,
                               parse_mode='HTML')


async def user_banned(language: str, user_id: int) -> bool:
    bans = await bot_storage.get_bans()
    key = str(user_id)

    if key in bans:
        logger.info(f'User id {key} found in bans {str(bans)}')

        try:
            text = locales.text(language, 'you_are_banned') + ' ' + bans[key]
            await bot.send_message(user_id, text)
            return True
        except Exception:
            logger.exception("Failed to apply ban")

    return False


async def invite_to_enter_email_password(user_id: int,
                                         state: FSMContext,
                                         extra_message: str = '') -> None:
    async with state.proxy() as data:
        current_state = await state.get_state()
        language = await get_ui_lang(data=data)

    if current_state != Form.email_password.state:
        await states_stack.add(user_id)

    await Form.email_password.set()

    text = f'{extra_message} {locales.text(language, "invite_email_password")}'
    keyboard = await get_cancel_keyboard(data)
    await bot.send_message(user_id, text, reply_markup=keyboard)


async def set_violation_city(state: FSMContext, user_id: int, city: str):
    async with state.proxy() as data:
        entered_address = get_value(data, "violation_address")
        delete_saved_address(data, entered_address)

        if city in entered_address:
            violation_address = entered_address
        else:
            violation_address = f'{city}, {entered_address}'

        language = await get_ui_lang(data=data)

    await set_violation_address(user_id, violation_address, state)
    await print_violation_address_info(state, user_id)
    await ask_for_violation_time(user_id, language)


async def invite_to_send_message_to_user(
        data: FSMContextProxy,
        user_id: int,
        to_user_id: str,
        message_id: Optional[int] = None,
        user_to_message_to_reply: Optional[str] = None):
    data['user_to_reply'] = to_user_id
    data['message_to_reply'] = user_to_message_to_reply

    language = await get_ui_lang(data=data)
    text = locales.text(language, Form.message_to_user.state)
    keyboard = await get_cancel_keyboard(data)

    await bot.send_message(user_id,
                           text,
                           reply_markup=keyboard,
                           reply_to_message_id=message_id)

    await Form.message_to_user.set()


@dp.callback_query_handler(
    lambda call: call.data == '/appeal_template',
    state='*')
async def show_appel_text_template(call, state: FSMContext):
    await bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    logger.info(f'Показать шаблон обращения - '
                f'{str(user_id)}:{call.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        empty_input = locales.text(language, 'empty_input')

        appeal_data = {
            'violation_photo_page': 'https://page_with_all_violation_photos',
            'violation_vehicle_number': '1111 AA-1',
            'violation_address': 'г. Мінск, вул. Васіля Быкава 42',
            'violation_datetime': '01.05.2020 18.04',
            'violation_caption': 'Примечание по желанию отправителя.',

            'violation_attachments': [
                'https://violation_photo_1',
                'https://violation_photo_2',
                'https://violation_photo_3',
                'https://violation_photo_4',
            ],

            'sender_email': get_value(data,
                                      'sender_email',
                                      placeholder='example@example.com'),

            'sender_phone': get_value(data, 'sender_phone'),

            'sender_first_name': get_value(data,
                                           'sender_first_name',
                                           placeholder=empty_input),

            'sender_last_name': get_value(data,
                                          'sender_last_name',
                                          placeholder=empty_input),

            'sender_patronymic': get_value(data,
                                           'sender_patronymic',
                                           placeholder=empty_input),

        }

        fake_appeal_id = 12345
        appeal_text = get_appeal_text(appeal_data, user_id, fake_appeal_id),

        # idk why appeal_text becomes tuple, some kind of magic
        await send_appeal_textfile_to_user(appeal_text[0],
                                           language,
                                           user_id,
                                           fake_appeal_id)


@dp.callback_query_handler(
    lambda call: call.data == '/user_city_as_violations',
    state=Form.no_city_in_address)
async def choose_users_city(call, state: FSMContext):
    await bot.answer_callback_query(call.id)
    logger.info('Нажал на кнопку своего города как города нарушения - '
                f'{str(call.from_user.id)}:{call.from_user.username}')

    async with state.proxy() as data:
        user_city = get_value(data, 'sender_city')

    await set_violation_city(state, call.message.chat.id, user_city)


@dp.callback_query_handler(lambda call: call.data == '/confirm_button',
                           state=Form.no_city_in_address)
async def address_is_full_click(call, state: FSMContext):
    await bot.answer_callback_query(call.id)
    logger.info('Подтвердил, что адрес с городом - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    language = await get_ui_lang(state)
    await print_violation_address_info(state, call.message.chat.id)
    await ask_for_violation_time(call.message.chat.id, language)


@dp.callback_query_handler(lambda call: '/change_receiver' in call.data,
                           state=Form.broadcasting)
async def change_receiver_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки выбора получателя броадкаста - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    current_receiver = call.data.replace('/change_receiver', '').strip()
    next_receiver = get_next_item(BROADCAST_RECEIVERS, current_receiver)

    async with state.proxy() as data:
        data['broadcast_receiver'] = next_receiver

    language = await get_ui_lang(state=state)
    text = get_broadcast_invitation(language, next_receiver)
    keyboard = get_broadcast_keyboard(language, next_receiver)

    await bot.edit_message_text(text,
                                call.message.chat.id,
                                call.message.message_id,
                                reply_markup=keyboard,
                                parse_mode='HTML')


@dp.callback_query_handler(lambda call: call.data == '/settings',
                           state='*')
async def settings_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки настроек - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await show_settings(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/personal_info',
                           state='*')
async def personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки показа личных данных - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await show_personal_info(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/enter_password',
                           state='*')
async def enter_password_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода email пароля - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await invite_to_enter_email_password(call.message.chat.id, state)


@dp.callback_query_handler(lambda call: call.data == '/delete_password',
                           state='*')
async def delete_password_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки удаления email пароля - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        data['sender_email_password'] = ''
        language = await get_ui_lang(data=data)

    text = locales.text(language, 'email_password_deleted')
    await bot.send_message(call.message.chat.id, text)


@dp.callback_query_handler(lambda call: call.data == '/language_settings',
                           state='*')
async def language_settings_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки языковых настроек - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        await send_language_info(call.message.chat.id, data)


@dp.callback_query_handler(
    lambda call: call.data == '/clear_saved_violation_addresses',
    state='*')
async def clear_saved_violation_addresses_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки очистки предыдущих адресов - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        data.pop('previous_violation_addresses', None)

    text = locales.text(language, 'saved_violation_addresses_deleted')
    await bot.answer_callback_query(call.id, text)


@dp.callback_query_handler(lambda call: call.data == '/appeal_email',
                           state='*')
async def appeal_email_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки пороля емаила - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        await send_appeal_email_info(call.message.chat.id, data)


@dp.callback_query_handler(lambda call: call.data == '/enter_personal_info',
                           state='*')
async def enter_personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода личных данных - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await ask_for_sender_info(call.message,
                              state,
                              str(Form.sender_first_name.state))


@dp.callback_query_handler(lambda call: call.data == '/verify_email',
                           state='*')
async def verify_email_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки верификации почты - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    if await verified_email(state):
        text = locales.text(language, 'email_already_verified')
        await bot.send_message(call.message.chat.id, text)
        return

    async with state.proxy() as data:
        secret_code = await mail_verifier.verify(get_value(data,
                                                           'sender_email'),
                                                 language)

    if secret_code == config.VERIFYING_FAIL:
        text = locales.text(language, 'email_verifying_fail')

        await Form.operational_mode.set()
    else:
        text = locales.text(language, Form.email_verifying.state) + '\n' +\
            locales.text(language, 'spam_folder')

        async with state.proxy() as data:
            data['secret_code'] = secret_code

        await Form.email_verifying.set()

    await bot.send_message(call.message.chat.id, text)


@dp.callback_query_handler(lambda call: call.data == '/reset',
                           state='*')
async def delete_personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки удаления личных данных - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await cmd_reset(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/forward_button',
                           state=SENDER_INFO)
async def sender_info_forward(call, state: FSMContext):
    current_form = await state.get_state()

    logger.info(f'Кнопка вперед {current_form} - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    next_form = get_next_item(SENDER_INFO, current_form)
    await ask_for_sender_info(call.message, state, next_form, edit=True)


@dp.callback_query_handler(lambda call: call.data == '/back_button',
                           state=SENDER_INFO)
async def sender_info_back(call, state: FSMContext):
    current_form = await state.get_state()

    logger.info(f'Кнопка назад {current_form} - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    next_form = get_next_item(REVERSED_SENDER_INFO, current_form)
    await ask_for_sender_info(call.message, state, next_form, edit=True)


@dp.callback_query_handler(lambda call: call.data == '/change_ui_language',
                           state='*')
async def change_ui_language_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки смены языка бота - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        if await get_ui_lang(data=data) == config.RU:
            data['ui_lang'] = config.BY
        elif await get_ui_lang(data=data) == config.BY:
            data['ui_lang'] = config.RU
        else:
            data['ui_lang'] = config.RU

        text, keyboard = await get_language_text_and_keyboard(data)

    try:
        await bot.edit_message_text(text,
                                    call.message.chat.id,
                                    call.message.message_id,
                                    reply_markup=keyboard,
                                    parse_mode='HTML')
    except MessageNotModified:
        pass


@dp.callback_query_handler(lambda call: '/police_response' in call.data,
                           state=Form.operational_mode)
async def police_response_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ответГАИ - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    if too_early_police_button(call.message.date):
        logger.info('Слишком рано нажата кнопка ответГАИ - ' +
                    f'{str(call.from_user.id)}:{call.from_user.username}')

        language = await get_ui_lang(state=state)
        await tell_that_too_early(call.message.chat.id, language)
        return

    violation_post_url: str = call.data.replace('/police_response', '')

    await ask_for_police_response(state,
                                  call.message.chat.id,
                                  violation_post_url)


@dp.callback_query_handler(lambda call: call.data == '/change_letter_language',
                           state='*')
async def change_letter_language_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки смены языка писем - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        if get_value(data, 'letter_lang') == config.RU:
            data['letter_lang'] = config.BY
        elif get_value(data, 'letter_lang') == config.BY:
            data['letter_lang'] = config.RU
        else:
            data['letter_lang'] = config.RU

        text, keyboard = await get_language_text_and_keyboard(data)

    try:
        await bot.edit_message_text(text,
                                    call.message.chat.id,
                                    call.message.message_id,
                                    reply_markup=keyboard,
                                    parse_mode='HTML')
    except MessageNotModified:
        pass


@dp.callback_query_handler(lambda call: call.data == '/finish_button',
                           state=[Form.sender_first_name,
                                  Form.sender_last_name,
                                  Form.sender_patronymic,
                                  Form.sender_email,
                                  Form.sender_phone,
                                  Form.sender_city,
                                  Form.sender_street,
                                  Form.sender_house,
                                  Form.sender_block,
                                  Form.sender_flat,
                                  Form.sender_zipcode])
async def finish_entering_personal_data(call, state: FSMContext):
    logger.info('Кнопка завершения ввода личных данных - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await show_private_info_summary(call.message.chat.id, state)


@dp.callback_query_handler(lambda call: call.data == '/current_time',
                           state=Form.violation_datetime)
async def current_time_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода текущего времени - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    current_time = get_str_current_time()

    message = await bot.send_message(call.message.chat.id, current_time)
    await catch_violation_time(message, state)


@dp.callback_query_handler(lambda call: call.data == '/yesterday',
                           state=Form.violation_datetime)
async def yesterday_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки вчера - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    await react_to_time_button(call.message.chat.id,
                               call.message.message_id,
                               state,
                               day_to_shift=-1)


@dp.callback_query_handler(lambda call: call.data == '/before_yesterday',
                           state=Form.violation_datetime)
async def before_yesterday_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки позавчера - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    await react_to_time_button(call.message.chat.id,
                               call.message.message_id,
                               state,
                               day_to_shift=-2)


@dp.callback_query_handler(lambda call: call.data == '/enter_violation_addr',
                           state=Form.violation_datetime)
async def violation_address_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода адреса нарушения - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        await ask_for_violation_address(call.message.chat.id, data)


@dp.callback_query_handler(lambda call: call.data == '/enter_recipient',
                           state=Form.violation_datetime)
async def recipient_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода реципиента - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    # этот текст не менять или менять по всему файлу
    text = locales.text(language, 'choose_recipient')

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    for region in territory.regions():
        if region == config.MINSK:
            postfix = ' ▶️'
            callback_data = 'minsk_menu'
        else:
            postfix = ''
            callback_data = region

        button = types.InlineKeyboardButton(
            text=locales.text(language, region) + postfix,
            callback_data=callback_data)

        keyboard.add(button)

    await bot.send_message(call.message.chat.id,
                           text,
                           reply_markup=keyboard)

    await Form.recipient.set()


@dp.callback_query_handler(lambda call: call.data == 'minsk_menu',
                           state=Form.recipient)
async def recipient_minsk_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки в подрегионы - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    button = types.InlineKeyboardButton(
        text=locales.text(language, config.MINSK),
        callback_data=config.MINSK)

    keyboard.add(button)

    for region in territory.regions(config.MINSK):
        button = types.InlineKeyboardButton(
            text=locales.text(language, region),
            callback_data=region)

        keyboard.add(button)

    await bot.edit_message_reply_markup(call.message.chat.id,
                                        call.message.message_id,
                                        reply_markup=keyboard)


@dp.callback_query_handler(
    lambda call: locales.text_exists('choose_recipient', call.message.text),
    state=Form.recipient)
async def recipient_choosen_click(call, state: FSMContext):
    logger.info('Выбрал реципиента - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        save_recipient(data, call.data)
        language = await get_ui_lang(data=data)

    await print_violation_address_info(state, call.message.chat.id)
    await ask_for_violation_time(call.message.chat.id, language)


@dp.callback_query_handler(lambda call: call.data == '/enter_violation_info',
                           state=[Form.violation_photo,
                                  Form.sending_approvement])
async def enter_violation_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода инфы о нарушении - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        # зададим сразу пустое примечание
        set_default(data, 'violation_caption')
        await ask_for_violation_address(call.message.chat.id, data)


@dp.callback_query_handler(lambda call: call.data == '/add_caption',
                           state=[Form.sending_approvement])
async def add_caption_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода примечания - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        # зададим сразу пустое примечание
        set_default(data, 'violation_caption')
        language = await get_ui_lang(data=data)

    await states_stack.add(call.message.chat.id)
    text = locales.text(language, Form.caption.state)

    async with state.proxy() as data:
        keyboard = await get_cancel_keyboard(data)

    await bot.send_message(call.message.chat.id, text, reply_markup=keyboard)
    await Form.caption.set()


@dp.callback_query_handler(lambda call: call.data == '/all_selected',
                           state=Form.vehicle_number)
async def numberplates_entered_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки завершения ввода гос. номера - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    async with state.proxy() as data:
        current_numberplates: str = \
            get_value(data, 'violation_vehicle_number', '')

        current_numberplates = current_numberplates.strip()
        language = await get_ui_lang(data=data)

        if not current_numberplates:
            text = locales.text(language, 'need_to_choose_number')
            await bot.answer_callback_query(call.id, text)
            return

        await bot.answer_callback_query(call.id)
        await ask_for_sending_approvement(call.message.chat.id, data)


@dp.callback_query_handler(lambda call: call.data == '/stop_recognition_magic',
                           state=Form.vehicle_number)
async def stop_recognition_magic_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки остановки распознавания - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await photo_manager.cancel_recognition_task(call.from_user.id)


@dp.callback_query_handler(lambda call: '/reply_to_user' in call.data,
                           state='*')
async def reply_to_user_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ответа на сообщение - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await states_stack.add(call.message.chat.id)

    async with state.proxy() as data:
        reply_data = call.data.replace('/reply_to_user', '').split()

        await invite_to_send_message_to_user(
            data,
            user_id=call.from_user.id,
            to_user_id=reply_data[0],
            message_id=call.message.message_id,
            user_to_message_to_reply=reply_data[1])


@dp.callback_query_handler(lambda call: '/numberplate' in call.data,
                           state=Form.vehicle_number)
async def select_numberplate(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки выбора распознанного номера - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')
    await bot.answer_callback_query(call.id)
    numberplate = call.data.replace('/numberplate', '')
    numberplate = prepare_registration_number(numberplate)

    async with state.proxy() as data:
        if numberplate in data['violation_vehicle_number']:
            data = delete_numberplate_from_user_data(data, numberplate)
        else:
            data = add_numberplate_to_user_data(data, numberplate)

        await ask_for_numberplate(call.message.chat.id,
                                  data,
                                  call.message.message_id)


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.violation_photo,
                                  Form.vehicle_number,
                                  Form.violation_datetime,
                                  Form.violation_address,
                                  Form.sending_approvement,
                                  Form.recipient,
                                  Form.no_city_in_address])
async def cancel_violation_input(call, state: FSMContext):
    logger.info('Отмена, возврат в рабочий режим - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

        delete_prepared_violation(data)
        await photo_manager.clear_storage(call.message.chat.id,
                                          with_files=True)

    await Form.operational_mode.set()
    await send_form_message(Form.operational_mode.state,
                            call.message.chat.id,
                            language)


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.feedback,
                                  Form.message_to_user,
                                  Form.broadcasting,
                                  Form.caption,
                                  Form.email_password,
                                  Form.police_response])
async def cancel_input(call, state: FSMContext):
    logger.info('Отмена, возврат в предыдущий режим - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await pop_saved_state(call.message.chat.id, call.message.from_user.id)


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.entering_captcha])
async def cancel_captcha_input(call, state: FSMContext):
    logger.info('Отмена, возврат в предыдущий режим - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:

        await rabbit_http.send_cancel(
            get_value(data, 'appeal_id'),
            call.message.chat.id,
            get_value(data, 'appeal_response_queue'))

        await delete_appeal_from_user_queue(data,
                                            call.message.chat.id,
                                            get_value(data, 'appeal_id'))

        data['appeal_id'] = 0

    await cancel_input(call, state)


@dp.callback_query_handler(lambda call: call.data == '/approve_sending',
                           state=Form.entering_captcha)
async def send_appeal_in_progress(call, state: FSMContext):
    logger.info('Нажатие кнопки отправки когда уже отправляется - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    text = locales.text(language, 'letter_sending_in_progress')

    await bot.send_message(call.message.chat.id, text)


@dp.callback_query_handler(lambda call: call.data == '/approve_sending',
                           state=Form.operational_mode)
async def send_appeal_again(call, state: FSMContext):
    logger.info('Кнопка отправки еще раз - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    text = locales.text(language, 'send_appeal_again')

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    approve_sending_button = types.InlineKeyboardButton(
        text=locales.text(language, 'approve_sending_button'),
        callback_data='/approve_sending')

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(approve_sending_button, cancel)

    it_is_reply, appeal_id = get_original_appeal_id(call.message)

    await bot.send_message(call.message.chat.id,
                           text,
                           reply_markup=keyboard,
                           reply_to_message_id=appeal_id)

    await Form.sending_approvement.set()


@dp.callback_query_handler(lambda call: call.data == '/approve_sending',
                           state=Form.sending_approvement)
async def send_appeal_click(call, state: FSMContext):
    logger.info('Нажата кнопка отправки в ГАИ - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    await Form.entering_captcha.set()

    language = await get_ui_lang(state)

    if await invalid_credentials(state):
        text = locales.text(language, 'need_personal_info')

        logger.info('Обращение не отправлено, не введены личные данные - ' +
                    str(call.from_user.id))

        await bot.send_message(call.message.chat.id, text)

        async with state.proxy() as data:
            delete_prepared_violation(data)
            # appeal_id saved to retry sending when credentials will be filled
            it_is_reply, data['appeal_id'] = \
                get_original_appeal_id(call.message)

    elif not await verified_email(state):
        logger.info('Обращение не отправлено, email не подтвержден - ' +
                    f'{str(call.from_user.id)}:{call.from_user.username}')

        async with state.proxy() as data:
            await invite_to_confirm_email(data, call.message.chat.id)
            delete_prepared_violation(data)

    else:
        it_is_reply, appeal_id = get_original_appeal_id(call.message)

        if not it_is_reply:
            async with state.proxy() as data:
                await process_entered_violation(data,
                                                call.message.chat.id,
                                                appeal_id)

        await send_appeal(call.message.chat.id, appeal_id)
        return

    await Form.operational_mode.set()


@dp.callback_query_handler(lambda call: call.data == '/repeat_sending',
                           state=Form.operational_mode)
async def send_letter_again_click(call, state: FSMContext):
    logger.info('Нажата кнопка повторной отправки в ГАИ - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    _, appeal_id = get_original_appeal_id(call.message)
    await send_appeal(call.message.chat.id, appeal_id)
    await bot.answer_callback_query(call.id)


@dp.callback_query_handler(lambda call: call.data == '/repeat_sending',
                           state='*')
async def send_letter_again_click_wrong_mode(call, state: FSMContext):
    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    text = locales.text(language, 'operational_mode_only')
    await bot.send_message(call.message.chat.id, text)


@dp.callback_query_handler(
    lambda call: config.PREVIOUS_ADDRESS_PREFIX in call.data,
    state=Form.violation_address)
async def use_saved_address_button(call, state: FSMContext):
    await bot.answer_callback_query(call.id)
    logger.info(
        'Кнопка предыдущего адреса - ' +
        f'{str(call.message.from_user.id)}:{call.message.from_user.username}')

    language = await get_ui_lang(state)

    try:
        address_index = int(
            call.data.replace(config.PREVIOUS_ADDRESS_PREFIX, ''))
    except ValueError:
        # сказать, что что-то пошло не так
        logger.info(f'Какая-то хрень вместо предыдущего адреса: ' +
                    f'{call.message.text} - {str(call.message.from_user.id)}')

        text = locales.text(language, 'invalid_address')

        await bot.send_message(call.message.from_user.id,
                               text,
                               reply_to_message_id=call.message.message_id)

        async with state.proxy() as data:
            await ask_for_violation_address(call.message.from_user.id, data)

        return

    await use_saved_address(address_index, call.message, state)


@dp.callback_query_handler(state='*')
async def reject_button_click(call, state: FSMContext):
    logger.info('Беспорядочно кликает на кнопки - ' +
                f'{str(call.from_user.id)}:{call.from_user.username}')

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    text = locales.text(language, 'irrelevant_action')
    current_state = await state.get_state()
    text += "\n\n" + locales.text(language, current_state)

    await bot.send_message(call.message.chat.id, text)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
    """
    Conversation's entry point
    """
    logger.info('Старт работы бота - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)
    text = locales.text(language, 'greeting')
    await bot.send_message(message.chat.id, text)
    await Form.initial.set()
    await invite_to_fill_credentials(message.chat.id, state)


@dp.message_handler(commands=['broadcast'], state=Form.operational_mode)
async def cmd_broadcast(message: types.Message, state: FSMContext):
    """
    Send message to all users and social networks
    """
    logger.info('Сообщение широковещательное - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    if message.from_user.id != config.ADMIN_ID:
        logger.info(
            'A нет, не сообщение - ' +
            f'{str(message.from_user.id)}:{message.from_user.username}')

        return

    language = await get_ui_lang(state=state)
    receiver_id = SOCIAL_NETWORKS

    async with state.proxy() as data:
        data['broadcast_receiver'] = receiver_id

    text = get_broadcast_invitation(language, receiver_id)
    keyboard = get_broadcast_keyboard(language, receiver_id)
    await bot.send_message(message.chat.id, text, reply_markup=keyboard)
    await Form.broadcasting.set()


@dp.message_handler(commands=['msg'], state=Form.operational_mode)
async def cmd_message(message: types.Message, state: FSMContext):
    """
    Send message specific user
    """
    logger.info('Сообщение конкретному пользователю - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    if message.from_user.id != config.ADMIN_ID:
        logger.info(
            'A нет, не сообщение - ' +
            f'{str(message.from_user.id)}:{message.from_user.username}')

        return

    language = await get_ui_lang(state=state)
    text = locales.text(language, 'user_id_input')
    await bot.send_message(message.chat.id, text)
    await Form.user_id_input.set()


@dp.message_handler(commands=['message'], state=Form.operational_mode)
async def cmd_admin_message(message: types.Message, state: FSMContext):
    """
    Send message to user
    """
    logger.info('Админ пишет - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    if message.from_user.id != config.ADMIN_ID:
        logger.info('A нет, не пишет - ' + str(message.from_user.id))
        return

    user_id_or_name = message.text.replace('/message', '').strip()

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        data['user_to_reply'] = user_id_or_name

    text = locales.text(language, Form.message_to_user.state) + '\n' + \
        '\n' + user_id_or_name

    keyboard = await get_cancel_keyboard(data)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)
    await Form.message_to_user.set()


@dp.message_handler(commands=['stats'], state='*')
async def cmd_statistic(message: types.Message, state: FSMContext):
    """
    Show bot's statistic
    """
    logger.info('Показ статистики - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    statistic = await get_statistic()
    language = await get_ui_lang(state)
    total_users_count_text = locales.text(language, 'total_users')
    registered_users_count_text = locales.text(language, 'registered_users')
    appeals_sent_text = locales.text(language, 'appeals_sent')
    appeals_sent_today_text = locales.text(language, 'appeals_sent_today')

    appeals_sent_yesterday_text = locales.text(language,
                                               'appeals_sent_yesterday')

    appeal_queue_size_text = locales.text(language, 'appeal_queue_size')

    text = total_users_count_text.format(statistic['total_users']) +\
        '\n' +\
        registered_users_count_text.format(statistic['registered_users']) +\
        '\n' +\
        appeals_sent_text.format('~' + statistic['appeals_sent']) +\
        '\n' +\
        appeals_sent_today_text.format(statistic['appeals_sent_today']) +\
        '\n' +\
        appeals_sent_yesterday_text.format(
            statistic['appeals_sent_yesterday']) +\
        '\n' +\
        appeal_queue_size_text.format(statistic['appeal_queue_size'])

    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=['settings'], state='*')
async def show_settings_command(message: types.Message, state: FSMContext):
    logger.info('Показ настроек команда - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    await show_settings(message, state)


@dp.message_handler(commands=['banlist'], state='*')
async def banlist_user_command(message: types.Message):
    if message.chat.id != config.ADMIN_ID:
        return

    logger.info('Банлист - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    bans = await bot_storage.get_bans()

    await bot.send_message(message.chat.id,
                           json.dumps(bans,
                                      ensure_ascii=False,
                                      indent='    '))


@dp.message_handler(commands=['unban'], state='*')
async def unban_user_command(message: types.Message, state: FSMContext):
    if message.chat.id != config.ADMIN_ID:
        return

    language = await get_ui_lang(state)

    logger.info('Разбанил человека - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    user_id = message.text.replace('/unban', '', 1).strip()

    if not user_id:
        text = locales.text(language, 'banned_id_expected')
        await bot.send_message(message.chat.id, text)
        return

    bans = await bot_storage.get_bans()
    bans.pop(user_id, None)
    await bot_storage.set_bans(bans)

    text = f'{user_id} {locales.text(language, "unbanned_succesfully")}'
    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=['ban'], state='*')
async def ban_user_command(message: types.Message, state: FSMContext):
    if message.chat.id != config.ADMIN_ID:
        return

    language = await get_ui_lang(state)

    logger.info('Забанил человека - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    try:
        user_id: str
        caption: str
        user_id, caption = message.text.replace('/ban ', '', 1).split(' ', 1)
    except ValueError:
        text = locales.text(language, 'id_and_caption_expected')
        await bot.send_message(message.chat.id, text)
        return

    bans = await bot_storage.get_bans()
    bans[user_id] = caption
    await bot_storage.set_bans(bans)

    text = f'{user_id} {locales.text(language, "banned_succesfully")}'
    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=['reset'], state='*')
async def cmd_reset(message: types.Message, state: FSMContext):
    logger.info('Сброс бота - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)

    await state.finish()
    await Form.initial.set()

    text = locales.text(language, 'reset') + ' ¯\\_(ツ)_/¯'
    await bot.send_message(message.chat.id, text)
    await invite_to_fill_credentials(message.chat.id, state)


@dp.message_handler(commands=['help'], state='*')
async def cmd_help(message: types.Message, state: FSMContext):
    logger.info('Вызов помощи - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)
    changelog = "https://github.com/parkun-by/parkun-bot/blob/master/README.md"

    text = locales.text(language, 'manual_help') + '\n' +\
        '\n' +\
        locales.text(language, 'privacy_policy') + '\n' +\
        '\n' +\
        f'<a href="{changelog}">Changelog.</a>' + '\n' +\
        '\n' +\
        locales.text(language, 'feedback_help')

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    letter_template = types.InlineKeyboardButton(
        text=locales.text(language, 'letter_template_button'),
        callback_data='/appeal_template')

    keyboard.add(letter_template)

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML',
                           disable_web_page_preview=True)


@dp.message_handler(commands=['feedback'], state='*')
async def write_feedback(message: types.Message, state: FSMContext):
    logger.info('Хочет написать фидбэк - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        text = locales.text(language, Form.feedback.state)
        keyboard = await get_cancel_keyboard(data)
        data_to_save = {
            'user_to_reply': get_value(data, 'user_to_reply'),
            'message_to_reply': get_value(data, 'message_to_reply'),
        }

    current_state = await state.get_state()

    if current_state != Form.feedback.state:
        await states_stack.add(message.chat.id, data_to_save)

    user_id = message.chat.id
    await bot.send_message(user_id, text, reply_markup=keyboard)
    await Form.feedback.set()

    await schedule_auto_back(user_id,
                             str(Form.feedback.state),
                             str(current_state))


@dp.message_handler(content_types=types.ContentTypes.ANY, state=Form.feedback)
async def catch_feedback(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод фидбэка - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)

    text = f'{str(message.from_user.username)} ' + \
        f'{str(message.from_user.id)} {str(message.message_id)}'

    await bot.send_message(config.ADMIN_ID, text)

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    reply_button = types.InlineKeyboardButton(
        text=locales.text(language, 'reply_button'),
        callback_data=f'/reply_to_user ' +
        f'{str(message.from_user.id)} {message.message_id}')

    keyboard.add(reply_button)
    await message.send_copy(chat_id=config.ADMIN_ID, reply_markup=keyboard)
    text = locales.text(language, 'thanks_for_feedback')
    await bot.send_message(message.chat.id, text)
    await pop_saved_state(message.chat.id, message.from_user.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.user_id_input)
async def catch_user_id(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод id пользователя для сообщения - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        await invite_to_send_message_to_user(data,
                                             user_id=message.from_user.id,
                                             to_user_id=message.text,
                                             message_id=message.message_id)


@dp.message_handler(content_types=types.ContentType.ANY,
                    state=Form.message_to_user)
async def catch_message_to_user(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем сообщение для пользователя - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        feedback_chat_id = pop_value(data, 'user_to_reply')
        feedback_message_id = pop_value(data, 'message_to_reply')
        language = await get_ui_lang(data=data)

    keyboard = types.InlineKeyboardMarkup()

    reply_button = types.InlineKeyboardButton(
        text=locales.text(language, 'reply_button'),
        callback_data=f'/reply_to_user ' +
        f'{str(message.from_user.id)} {message.message_id}')

    keyboard.add(reply_button)

    try:
        await message.send_copy(feedback_chat_id,
                                reply_to_message_id=feedback_message_id,
                                reply_markup=keyboard)
    except ChatNotFound:
        text = locales.text(language,
                            'cant_find_user').format(feedback_chat_id)
        await bot.send_message(message.from_user.id, text)

    await pop_saved_state(message.chat.id, message.from_user.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.email_verifying)
async def catch_secret_code(message: types.Message, state: FSMContext):
    logger.info('Ввод секретного кода - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        secret_code = get_value(data, 'secret_code')
        language = await get_ui_lang(data=data)

    if secret_code == message.text:
        async with state.proxy() as data:
            data['verified'] = True

        text = locales.text(language, 'email_verified')
    else:
        text = locales.text(language, 'reply_verification') + '\n' +\
            locales.text(language, 'press_feedback')

    await bot.send_message(message.chat.id,
                           text,
                           parse_mode='HTML',
                           disable_web_page_preview=True)
    
    await Form.operational_mode.set()

    async with state.proxy() as data:
        if get_value(data, 'appeal_id'):
            await invite_to_send_violation_again(language,
                                                 message.chat.id,
                                                 data['appeal_id'],
                                                 'sending_allowed')
            data['appeal_id'] = 0


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_first_name)
async def catch_sender_first_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод имени - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)

    if not await check_validity(validator.first_name, message, language):
        await ask_for_sender_info(message,
                                  state,
                                  str(Form.sender_first_name.state))
        return

    async with state.proxy() as data:
        data['sender_first_name'] = message.text

    await ask_for_sender_info(message,
                              state,
                              str(Form.sender_patronymic.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_patronymic)
async def catch_sender_patronymic(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод отчества - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)

    if not await check_validity(validator.patronymic, message, language):
        await ask_for_sender_info(message,
                                  state,
                                  str(Form.sender_patronymic.state))
        return

    async with state.proxy() as data:
        data['sender_patronymic'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_last_name.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_last_name)
async def catch_sender_last_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод фамилии - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)

    if not await check_validity(validator.last_name, message, language):
        await ask_for_sender_info(message,
                                  state,
                                  str(Form.sender_last_name.state))
        return

    async with state.proxy() as data:
        data['sender_last_name'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_email.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_email)
async def catch_sender_email(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод email - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    try:
        if message.text.split('@')[1] in blocklist:
            logger.info(
                'Временный email - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

            text = locales.text(language, 'no_temporary_email')
            await bot.send_message(message.chat.id, text)
            await ask_for_sender_info(message,
                                      state,
                                      str(Form.sender_email.state))

            return
    except IndexError:
        pass

    async with state.proxy() as data:
        data['sender_email'] = message.text
        data['sender_email_password'] = ''
        data['verified'] = False

    await ask_for_sender_info(message, state, str(Form.sender_phone.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_phone)
async def catch_sender_phone(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод телефона - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        data['sender_phone'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_city.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_city)
async def catch_sender_city(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод города - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    if not await check_validity(validator.city, message, language):
        await ask_for_sender_info(message, state, str(Form.sender_city.state))
        return

    async with state.proxy() as data:
        data['sender_city'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_street.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_street)
async def catch_sender_street(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод улицы - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    if not await check_validity(validator.street, message, language):
        await ask_for_sender_info(message,
                                  state,
                                  str(Form.sender_street.state))
        return

    async with state.proxy() as data:
        data['sender_street'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_block.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_house)
async def catch_sender_house(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод дома - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    if not await check_validity(validator.building, message, language):
        await ask_for_sender_info(message, state, str(Form.sender_house.state))
        return

    async with state.proxy() as data:
        data['sender_house'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_flat.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_block)
async def catch_sender_block(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод корпуса - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        data['sender_block'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_house.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_flat)
async def catch_sender_flat(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод квартиры - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        data['sender_flat'] = message.text

    await ask_for_sender_info(message, state, str(Form.sender_zipcode.state))


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_zipcode)
async def catch_sender_zipcode(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод индекса - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')
    language = await get_ui_lang(state)

    if not await check_validity(validator.zipcode, message, language):
        return

    async with state.proxy() as data:
        data['sender_zipcode'] = message.text

    await show_private_info_summary(message.chat.id, state)


@dp.message_handler(content_types=types.ContentType.PHOTO,
                    state=Form.police_response)
async def police_response_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку фотки ответа ГАИ - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        response_violation_post_url = get_value(data, 'responsed_post_url')
        language = await get_ui_lang(data=data)

    photo_id = message.photo[-1]['file_id']

    photo_path = await photo_manager.store_photo(message.chat.id,
                                                 message.photo[-1],
                                                 message.message_id)

    text = locales.text(language, 'response_sended').format(config.CHANNEL)

    success_message = await bot.send_message(message.chat.id,
                                             text,
                                             parse_mode='HTML')

    await share_response_post(language,
                              response_violation_post_url,
                              photo_path,
                              photo_id,
                              message.chat.id,
                              message.message_id,
                              success_message.message_id)

    await Form.operational_mode.set()


@dp.message_handler(content_types=types.ContentTypes.TEXT,
                    state=Form.police_response)
async def police_response_text(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку текста ответа ГАИ - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        response_violation_post_url = get_value(data, 'responsed_post_url')
        language = await get_ui_lang(data=data)

    text = locales.text(language, 'response_sended').format(config.CHANNEL)

    success_message = await bot.send_message(message.chat.id,
                                             text,
                                             parse_mode='HTML')

    await share_response_post(language,
                              response_violation_post_url,
                              photo_path=None,
                              photo_id=None,
                              user_id=message.chat.id,
                              post_id=message.message_id,
                              reply_id=success_message.message_id,
                              text=message.text)

    await Form.operational_mode.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.broadcasting)
async def text_to_broadcast(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем широковещательный текстопост - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        receiver = pop_value(data, 'broadcast_receiver')
        language = await get_ui_lang(data=data)

    if receiver == SOCIAL_NETWORKS:
        await share_to_social_networks(message, str(types.ContentType.TEXT))
    elif receiver == USERS:
        await share_to_users(message)

    await Form.operational_mode.set()

    await send_form_message(Form.operational_mode.state,
                            message.from_user.id,
                            language)


@dp.message_handler(content_types=types.ContentType.PHOTO,
                    state=Form.broadcasting)
async def photo_to_broadcast(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем широковещательный фотопост - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        receiver = pop_value(data, 'broadcast_receiver')
        language = await get_ui_lang(data=data)

    if receiver == SOCIAL_NETWORKS:
        await share_to_social_networks(message, str(types.ContentType.PHOTO))
    elif receiver == USERS:
        await share_to_users(message)

    await Form.operational_mode.set()

    await send_form_message(Form.operational_mode.state,
                            message.from_user.id,
                            language)


@dp.message_handler(content_types=types.ContentType.ANY,
                    state=Form.broadcasting)
async def message_to_broadcast(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем широковещательный ANY - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        receiver = pop_value(data, 'broadcast_receiver')
        language = await get_ui_lang(data=data)

    if receiver == SOCIAL_NETWORKS:
        text = locales.text(language, 'simple_post_only')
        await bot.send_message(message.chat.id, text)
    elif receiver == USERS:
        await share_to_users(message)

    await Form.operational_mode.set()

    await send_form_message(Form.operational_mode.state,
                            message.from_user.id,
                            language)


@dp.message_handler(content_types=types.ContentType.PHOTO,
                    state=Form.operational_mode)
async def initial_violation_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку первой фотки - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)

    if await user_banned(language, message.from_user.id):
        return

    if post_from_channel(message):
        logger.info('Фотка из канала - ' + str(message.from_user.id))
        await police_response_sending(message, state)
    else:
        await photo_manager.clear_storage(message.chat.id)
        await process_violation_photo(message, state)


@dp.message_handler(content_types=types.ContentType.PHOTO,
                    state=Form.violation_photo)
async def process_violation_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку еще фотки нарушения - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)

    # Проверим есть ли место под еще одно фото нарушения
    if await violation_storage_full(state):
        text = locales.text(language, 'violation_storage_full') +\
            str(config.MAX_VIOLATION_PHOTOS)
    else:
        async with semaphore, state.proxy() as data:
            # Добавляем фотку наилучшего качества(последнюю в массиве) в список
            # прикрепления в письме
            await add_photo_to_attachments(message.photo[-1],
                                           data,
                                           message.chat.id)

        text = locales.text(language, Form.violation_photo.state) + '\n' +\
            '\n' +\
            '👮🏻‍♂️' + ' ' + locales.text(language, 'photo_quality_warning')

    keyboard = get_photo_step_keyboard(language)

    await message.reply(text,
                        reply_markup=keyboard,
                        parse_mode='HTML',
                        disable_web_page_preview=True)

    await Form.violation_photo.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.vehicle_number)
async def catch_vehicle_number(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод гос. номера - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    async with state.proxy() as data:
        if current_enter := get_value(data, 'violation_vehicle_number', ''):
            entered_number = prepare_registration_number(message.text)

            if not already_entered(entered_number, current_enter):
                data['violation_vehicle_number'] += f', {entered_number}'
        else:
            data['violation_vehicle_number'] = \
                prepare_registration_number(message.text)

        await ask_for_sending_approvement(message.chat.id, data)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.caption)
async def catch_caption(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод примечания - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    await pop_saved_state(message.chat.id, message.from_user.id)

    async with state.proxy() as data:
        data['violation_caption'] = message.text.strip()
        await ask_for_sending_approvement(message.chat.id, data)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.email_password)
async def catch_email_password(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод пароля email - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')
    password = message.text.strip()

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        email = get_value(data, 'sender_email')

        if not await Email(loop).check_connection(email, password):
            text = locales.text(
                language,
                'invalid_email_password').format(email, password)

            await invite_to_enter_email_password(message.chat.id, state, text)
            return

        data['sender_email_password'] = password

    text = locales.text(language, 'email_password_saved').format(email)
    await bot.send_message(message.chat.id, text)
    await pop_saved_state(message.chat.id, message.from_user.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.no_city_in_address)
async def catch_violation_city(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод города нарушения - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    await set_violation_city(state, message.chat.id, message.text)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_address)
async def catch_violation_address(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса нарушения - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    if address_too_short(message.text):
        logger.info(
            'Слишком короткий адрес - ' +
            f'{str(message.from_user.id)}:{message.from_user.username}')

        async with state.proxy() as data:
            await message_about_short_address(message.from_user.id, data)
            await ask_for_violation_address(message.from_user.id, data)

        return

    if option := get_previos_address_number(message.text):
        await use_saved_address(option, message, state)
        return

    await set_violation_address(message.chat.id, message.text, state)
    language = await get_ui_lang(state)

    if maybe_no_city_in_address(message.text):
        logger.info(
            f'Адрес без города: {message.text} - ' +
            f'{str(message.from_user.id)}:{message.from_user.username}')

        await ask_about_short_address(state, message.chat.id)
    else:
        await print_violation_address_info(state, message.chat.id)
        await ask_for_violation_time(message.chat.id, language)


@dp.message_handler(content_types=types.ContentType.LOCATION,
                    state=Form.violation_address)
async def catch_gps_violation_location(message: types.Message,
                                       state: FSMContext):
    logger.info('Обрабатываем ввод локации адреса нарушения - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    coordinates = [message.location.longitude, message.location.latitude]

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        address = await locator.get_address(coordinates,
                                            get_value(data, 'letter_lang'))

        if address == config.ADDRESS_FAIL:
            address = locales.text(language, 'no_address_detected')

        region = await locator.get_region(coordinates)
        save_recipient(data, region)
        region = get_value(data, 'recipient')

    if address is None:
        logger.info(
            'Не распознал локацию - ' +
            f'{str(message.from_user.id)}:{message.from_user.username}')

        text = locales.text(language, 'cant_locate')
        await bot.send_message(message.chat.id, text)
        return

    async with state.proxy() as data:
        await save_violation_address(address, coordinates, data)

    await print_violation_address_info(state, message.chat.id)
    await ask_for_violation_time(message.chat.id, language)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_datetime)
async def catch_violation_time(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод даты и времени нарушения - ' +
                f'{str(message.chat.id)}:{message.chat.username}')

    async with state.proxy() as data:
        datetime = datetime_parser.get_violation_datetime(
            get_value(data, 'violation_date'),
            message.text)

        if not datetime:
            logger.info(
                'Неправильно ввел датовремя - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

            language = await get_ui_lang(data=data)
            text = locales.text(language, 'invalid_datetime')
            await bot.send_message(message.chat.id, text)
            await ask_for_violation_time(message.chat.id, language)
            return

        data['violation_datetime'] = datetime
        await ask_for_numberplate(message.chat.id, data)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.entering_captcha)
async def catch_captcha(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод капчи - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    await Form.operational_mode.set()

    async with state.proxy() as data:
        await send_captcha_text(state,
                                message.chat.id,
                                message.text,
                                get_value(data, 'appeal_id'))

        data['appeal_id'] = 0

    await pop_saved_state(message.chat.id, message.from_user.id)


@dp.message_handler(content_types=types.ContentTypes.ANY, state=Form.initial)
async def ignore_initial_input(message: types.Message, state: FSMContext):
    await invite_to_fill_credentials(message.chat.id, state)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=Form.operational_mode)
async def reject_wrong_input(message: types.Message, state: FSMContext):
    logger.info('Посылает не фотку, а что-то другое - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)
    text = locales.text(language, Form.operational_mode.state)

    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=Form.police_response)
async def reject_wrong_police_response_input(message: types.Message,
                                             state: FSMContext):
    language = await get_ui_lang(state)
    text = locales.text(language, 'photo_or_text')

    async with state.proxy() as data:
        keyboard = await get_cancel_keyboard(data)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=Form.violation_photo)
async def reject_wrong_violation_photo_input(message: types.Message,
                                             state: FSMContext):
    language = await get_ui_lang(state)
    text = locales.text(language, Form.violation_photo.state)
    keyboard = get_photo_step_keyboard(language)
    await bot.send_message(message.chat.id, text, reply_markup=keyboard)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=[Form.vehicle_number,
                           Form.violation_datetime,
                           Form.violation_address,
                           Form.caption,
                           Form.sender_first_name,
                           Form.sender_last_name,
                           Form.sender_patronymic,
                           Form.sender_email,
                           Form.sender_phone,
                           Form.sender_city,
                           Form.sender_street,
                           Form.sender_house,
                           Form.sender_block,
                           Form.sender_flat,
                           Form.sender_zipcode,
                           Form.entering_captcha,
                           Form.email_password,
                           Form.no_city_in_address,
                           Form.user_id_input])
async def reject_non_text_input(message: types.Message, state: FSMContext):
    logger.info('Посылает не текст, а что-то другое - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)
    text = locales.text(language, 'text_only')

    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=[Form.sending_approvement,
                           Form.recipient])
async def ask_for_button_press(message: types.Message, state: FSMContext):
    logger.info('Нужно нажать на кнопку - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    language = await get_ui_lang(state)
    text = locales.text(language, 'buttons_only')

    async with state.proxy() as data:
        keyboard = await get_cancel_keyboard(data)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)


@dp.message_handler(content_types=types.ContentTypes.ANY, state=None)
async def no_state(message: types.Message, state: FSMContext):
    logger.info('Нет стейта - ' +
                f'{str(message.from_user.id)}:{message.from_user.username}')

    await cmd_start(message, state)


async def create_global_objects():
    global bot_storage
    bot_storage = await BotStorage.create()

    global locator
    locator = Locator(loop)

    executors = {
        CANCEL_ON_IDLE: maybe_return_to_state,
        RELOAD_BOUNDARY: locator.get_boundary,
    }

    global scheduler
    scheduler = Scheduler(bot_storage, executors, loop)

    locator.scheduler = scheduler

    global statistic
    statistic = Statistic(bot_storage)

    global photo_manager
    photo_manager = await PhotoManager.create(loop, bot)


async def startup(dispatcher: Dispatcher):
    logger.info('Старт бота.')
    await create_global_objects()
    logger.info('Подключаемся к очереди статусов обращений.')
    asyncio.ensure_future(rabbit_amqp.start(loop, status_received))
    logger.info('Подключились.')
    logger.info('Загружаем границы регионов.')
    asyncio.ensure_future(locator.download_boundaries())
    logger.info('Запускаем планировщик.')
    asyncio.ensure_future(scheduler.start())


async def shutdown(dispatcher: Dispatcher):
    logger.info('Убиваем бота.')

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
