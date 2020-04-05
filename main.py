import asyncio
import io
import logging
import json
import copy
import sys
from datetime import datetime
from typing import Any, Optional, Tuple, Union, List, Callable
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types.photo_size import PhotoSize

from dateutil import tz
from aiogram import Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters.state import State
from aiogram.utils import executor
from aiogram.utils.exceptions import BadRequest as AiogramBadRequest, \
    MessageNotModified
from disposable_email_domains import blocklist

import config
from appeal_text import AppealText
from locator import Locator
from mail_verifier import MailVerifier
from photoitem import PhotoItem
from states import Form
from photo_manager import PhotoManager
from locales import Locales
from broadcaster import Broadcaster
from validator import Validator
from http_rabbit import Rabbit as HTTPRabbit
from amqp_rabbit import Rabbit as AMQPRabbit
from imap_email import Email
from states_stack import StatesStack
import datetime_parser
from appeal_summary import AppealSummary
import territory


logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger("parkun_bot")

loop = asyncio.get_event_loop()
bot = Bot(token=config.API_TOKEN, loop=loop)

storage = RedisStorage2(host=config.REDIS_HOST,
                        port=config.REDIS_PORT,
                        password=config.REDIS_PASSWORD)

dp = Dispatcher(bot, storage=storage)
locator = Locator(loop)
mail_verifier = MailVerifier()
semaphore = asyncio.Semaphore()
locales = Locales()
validator = Validator()
http_rabbit = HTTPRabbit()
amqp_rabbit = AMQPRabbit()
photo_manager = PhotoManager(loop)


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


broadcaster = Broadcaster(get_value, locales)


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


def commer(text: str) -> str:
    if text:
        return f'{text}, '

    return text


async def cancel_sending(user_id: int, appeal_id: int, text_id: str) -> None:
    logger.info(f'Время вышло - {user_id}')
    await pop_saved_state(user_id, user_id)
    state = dp.current_state(chat=user_id, user=user_id)

    async with state.proxy() as data:
        await delete_appeal_from_user_queue(data,
                                            user_id,
                                            appeal_id)

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
}

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

    # настроим клавиатуру
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

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    verify_email_button = types.InlineKeyboardButton(
        text=locales.text(language, 'verify_email_button'),
        callback_data='/verify_email')

    keyboard.add(verify_email_button)

    await bot.send_message(chat_id,
                           message,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def send_appeal_textfile_to_user(appeal_text, language, chat_id):
    appeal_text = convert_for_windows(appeal_text)
    file = io.StringIO(appeal_text)
    file.name = locales.text(language, 'letter_html')
    await bot.send_document(chat_id, file)


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


async def send_violation_to_channel(language: str,
                                    date_time: str,
                                    location: str,
                                    plate: str,
                                    photos_id: list) -> None:
    caption = get_violation_caption(language, date_time, location, plate)

    # в канал
    await send_photos_group_with_caption(photos_id,
                                         config.CHANNEL,
                                         caption)


async def compose_appeal(data: FSMContextProxy,
                         chat_id: int,
                         appeal_id: int) -> dict:
    appeal = {
        'type': config.APPEAL,
        'text': get_appeal_text(data),
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
        'sender_email': get_appeal_email(data),
        'sender_email_password': get_value(data, 'sender_email_password'),
        'user_id': chat_id,
        'appeal_id': appeal_id,
    }

    for key in VIOLATION_INFO_KEYS:
        appeal[key] = get_value(data, key)

    return appeal


async def send_success_sending(user_id: int, appeal_id: int) -> None:
    logger.info(f'Успешно отправлено - {str(user_id)}')
    state = dp.current_state(chat=user_id, user=user_id)
    language = await get_ui_lang(state)
    text = locales.text(language, 'successful_sending')
    await bot.send_message(user_id,
                           text,
                           parse_mode='HTML',
                           reply_to_message_id=appeal_id)

    async with state.proxy() as data:
        appeal = get_appeal_from_user_queue(data, appeal_id)

        if appeal:
            await postsending_operations(language, user_id, appeal)

        await delete_appeal_from_user_queue(data, user_id, appeal_id)


async def postsending_operations(language: str,
                                 user_id: int,
                                 appeal: dict) -> None:
    await send_appeal_textfile_to_user(appeal['text'], language, user_id)

    await send_violation_to_channel(language,
                                    appeal['violation_datetime'],
                                    appeal['violation_address'],
                                    appeal['violation_vehicle_number'],
                                    appeal['violation_photo_ids'])

    logger.info(f'Отправили в канал - {str(user_id)}')

    await broadcaster.share(language,
                            appeal['violation_photo_files_paths'],
                            appeal['violation_location'],
                            appeal['violation_datetime'],
                            appeal['violation_vehicle_number'],
                            appeal['violation_address'])

    logger.info(f'Отправили в остальное - {str(user_id)}')


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

    await state.set_state(Form.entering_captcha)


async def send_appeal(user_id: int, appeal_id: int) -> None:
    logger.info(f'Шлем обращение - {user_id}')
    state = dp.current_state(chat=user_id, user=user_id)

    async with state.proxy() as data:
        delete_prepared_violation(data)
        appeal = get_appeal_from_user_queue(data, appeal_id)

        if not appeal:
            await parse_appeal_from_message(data, user_id, appeal_id)
            return

        await http_rabbit.send_appeal(appeal, user_id)

        language = await get_ui_lang(data=data)
        text = locales.text(language, 'appeal_sent')

        logger.info(f'Обращение {str(appeal_id)} ' +
                    f'поставлено в очередь - {str(user_id)}')

        await bot.send_message(user_id, text)
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

    await Form.sending_approvement.set()
    await approve_sending(user_id, data)


async def process_entered_violation(data: FSMContextProxy,
                                    user_id: int,
                                    appeal_id: int) -> dict:
    await get_prepared_photos(data, user_id, appeal_id)
    appeal = await compose_appeal(data, user_id, appeal_id)
    add_appeal_to_user_queue(data, appeal, appeal_id)
    delete_prepared_violation(data)
    return appeal


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
                                       photos_message.chat.id)

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
    sender_data = json.loads(status)
    queue_id = str(get_value(sender_data, 'answer_queue', 'undefined'))

    logger.info(f'Прилетел статус: ' +
                f'{str(sender_data["user_id"])} - {queue_id} - ' +
                f'{sender_data["type"]}')

    user_id = int(sender_data['user_id'])
    appeal_id = int(sender_data['appeal_id'])

    if sender_data['type'] == config.OK:
        asyncio.run_coroutine_threadsafe(
            send_success_sending(user_id, appeal_id),
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


async def reply_that_captcha_ok(user_id: int, appeal_id: int) -> None:
    state = dp.current_state(chat=user_id, user=user_id)
    language = await get_ui_lang(state)
    text = text = locales.text(language, 'captcha_ok')

    await bot.send_message(user_id,
                           text,
                           reply_to_message_id=appeal_id,
                           disable_notification=True)


def get_appeal_email(data) -> Optional[str]:
    if get_value(data, 'sender_email_password', ''):
        return get_value(data, 'sender_email', '')


async def send_captcha_text(state: FSMContext,
                            chat_id: int,
                            captcha_text: str,
                            appeal_id: int) -> None:
    logger.info(f'Посылаем текст капчи - {chat_id}')

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        appeal_email = get_appeal_email(data)

    try:
        await http_rabbit.send_captcha_text(
            captcha_text,
            chat_id,
            appeal_id,
            appeal_email,
            get_value(data, 'appeal_response_queue'))

    except Exception as exc:
        text = locales.text(language, 'sending_failed') + '\n' + str(exc)
        logger.error('Неудачка - ' + str(chat_id) + '\n' + str(exc))
        await bot.send_message(chat_id, text)


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

        if data['violation_photos_amount'] < config.MAX_VIOLATION_PHOTOS:
            data['violation_photos_amount'] += 1
            return False
        else:
            return True


async def add_photo_to_attachments(photo: PhotoSize,
                                   data: FSMContextProxy,
                                   user_id: int) -> None:
    ensure_attachments_availability(data)
    data['violation_photo_ids'].append(photo['file_id'])


async def get_temp_photo_url(photo_id: str) -> str:
    file = await bot.get_file(photo_id)
    return config.URL_BASE + file.file_path


async def prepare_photos(data: FSMContextProxy,
                         user_id: int,
                         appeal_id: int) -> None:
    await photo_manager.clear_storage(user_id, appeal_id)
    urls_tasks = map(get_temp_photo_url, data['violation_photo_ids'])
    urls = asyncio.gather(*urls_tasks)

    for url in await urls:
        photo_manager.stash_photo(user_id, appeal_id, url)

    violation_summary = get_violation_caption(
        await get_ui_lang(data=data),
        data['violation_datetime'],
        data['violation_address'],
        data['violation_vehicle_number']
    )

    photo_manager.stash_page(user_id, appeal_id, violation_summary)


async def get_prepared_photos(data: FSMContextProxy,
                              user_id: int,
                              appeal_id: int):
    photos_data = await photo_manager.get_photo_data(user_id, appeal_id)

    for image_url in photos_data['urls']:
        image_url = remove_http(image_url)
        data['violation_attachments'].append(image_url)

    for image_path in photos_data['file_paths']:
        data['violation_photo_files_paths'].append(image_path)

    page_url = remove_http(photos_data['page_url'])
    data['violation_photo_page'] = page_url

    logger.info('Вгрузили фоточки - ' + str(user_id))


def remove_http(url: str) -> str:
    return url.replace('https://', '').replace('http://', '')


def delete_prepared_violation(data: FSMContextProxy) -> None:
    for key in VIOLATION_INFO_KEYS:
        set_default(data, key, force=True)

    data['appeal_response_queue'] = ''


def save_entered_address(data: FSMContextProxy, address: str):
    addresses = get_value(data, 'previous_violation_addresses')

    if address not in addresses:
        addresses.reverse()
        addresses.append(address)
        addresses.reverse()
    else:  # move element to first position
        addresses.insert(0, addresses.pop(addresses.index(address)))

    limit = 5

    while len(addresses) > limit:
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
        'banned_users': {},
        'violation_location': [],
        'states_stack': [],
        'violation_date': datetime_parser.get_current_datetime(),
        'previous_violation_addresses': [],
        'appeal_id': 0,
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
        logger.info(f'Это реплай - {str(message.from_user.username)}')
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
                                        appeal_id: int) -> None:
    appeals: dict = get_value(data, 'appeals')
    appeals.pop(str(appeal_id), 'default_value')
    data['appeals'] = appeals

    # также удалим временные файлы картинок нарушений
    await photo_manager.clear_storage(user_id, appeal_id)


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


def get_appeal_text(data: FSMContextProxy) -> str:
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
    }

    return AppealText.get(get_value(data, 'letter_lang'), violation_data)


async def approve_sending(user_id: int, data: FSMContextProxy) -> int:
    language = await get_ui_lang(data=data)

    caption_button_text = locales.text(language, 'add_caption_button')

    text = await appeal_summary.compose_summary(language, data)

    await send_photos_group_with_caption(
        get_value(data, 'violation_photo_ids'),
        user_id)

    if get_value(data, 'violation_caption'):
        caption_button_text = locales.text(language,
                                           'change_caption_button')

    # настроим клавиатуру
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

    await prepare_photos(data, user_id, message.message_id)
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


async def get_cancel_keyboard(data):
    language = await get_ui_lang(data=data)

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup()

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(cancel)

    return keyboard


async def get_sender_param_keyboard(language):
    # настроим клавиатуру
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
                              next_state: State,
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
        text = locales.text(language, text_key) + '\n'

    return text


async def show_private_info_summary(chat_id, state):
    language = await get_ui_lang(state)

    if await invalid_credentials(state):
        text = locales.text(language, 'no_info_warning')
        # настроим клавиатуру
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


async def ask_for_violation_address(chat_id, data):
    language = await get_ui_lang(data=data)

    text = locales.text(language, Form.violation_address.state) + '\n' +\
        locales.text(language, 'bot_can_guess_address') + '\n' +\
        '\n' +\
        locales.text(language, 'irrelevant_information_warning') + '\n' +\
        '\n' +\
        locales.text(language,
                     f'{Form.violation_address.state}_example') + '\n' +\
        '\n'

    # настроим клавиатуру
    keyboard = await get_cancel_keyboard(data)

    if get_value(data, 'previous_violation_addresses'):
        text += locales.text(language, 'previous_violation_addresses') + \
            '\n' + \
            '\n' + \
            get_saved_addresses_list(
                get_value(data, 'previous_violation_addresses'))

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.violation_address.set()


def get_saved_addresses_list(addresses: list) -> str:
    addresses_list = ''

    for number, address in enumerate(addresses):
        addresses_list += f'📍 {address} - ' + \
            f'{config.PREVIOUS_ADDRESS_PREFIX}{number}\n'

    return addresses_list


async def send_language_info(chat_id: int, data: FSMContextProxy) -> None:
    text, keyboard = await get_language_text_and_keyboard(data)

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def send_appeal_email_info(chat_id: int, data: FSMContextProxy) -> None:
    language = await get_ui_lang(data=data)
    email = get_value(data, 'sender_email')
    text = locales.text(language, 'email_password').format(email)

    # настроим клавиатуру
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

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


def save_recipient(data: FSMContextProxy, recipient: Optional[str]) -> None:
    if recipient is None:
        data['recipient'] = config.MINSK
    else:
        data['recipient'] = recipient


async def print_violation_address_info(state: FSMContext,
                                       chat_id: int) -> None:
    async with state.proxy() as data:
        address = get_value(data, 'violation_address')
        region = get_value(data, 'recipient')
        language = await get_ui_lang(data=data)

    text = locales.text(language, 'recipient') +\
        ' <b>{}</b>.'.format(locales.text(language, region)) + '\n' +\
        '\n' +\
        locales.text(language, 'violation_address') + \
        ' <b>{}</b>'.format(address)

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_violation_addr_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_violation_addr_button'),
        callback_data='/enter_violation_addr')

    enter_recipient_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_recipient'),
        callback_data='/enter_recipient')

    keyboard.add(enter_violation_addr_button, enter_recipient_button)

    await bot.send_message(chat_id,
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


async def ask_for_violation_time(chat_id, language):
    text, keyboard = compose_violation_time_asking(
        language,
        datetime_parser.get_current_datetime())

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.violation_datetime.set()


def get_violation_datetime_keyboard(
        language: str) -> types.InlineKeyboardMarkup:
    # настроим клавиатуру
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
                                         caption=''):
    photos = []

    for count, photo_id in enumerate(photos_id):
        text = ''

        # первой фотке добавим общее описание
        if count == 0:
            text = caption

        photo = PhotoItem('photo', photo_id, text)
        photos.append(photo)

    await bot.send_media_group(chat_id=chat_name, media=photos)


def prepare_registration_number(number: str):
    """replace all cyrillyc to latin"""

    kyrillic = 'АВСЕНКМОРТХУІ'
    latin = 'ABCEHKMOPTXYI'

    up_number = number.upper().strip()

    for num, symbol in enumerate(kyrillic):
        up_number = up_number.replace(symbol, latin[num])

    return up_number


async def ask_about_short_address(state: FSMContext, chat_id: int) -> None:
    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        user_city = get_value(data, 'sender_city')

    question = locales.text(language, 'short_address_check')

    # настроим клавиатуру
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

    await Form.short_address_check.set()


async def set_violation_address(chat_id: int,
                                address: str,
                                state: FSMContext) -> None:
    coordinates = await locator.get_coordinates(address)
    recipient = await locator.get_region(coordinates)

    async with state.proxy() as data:
        await save_violation_address(address, coordinates, data)
        save_recipient(data, recipient)


def maybe_no_city_in_address(address: str) -> bool:
    if 'г.' in address:
        return False

    address = address.replace('вул.', '').replace('зав.', '') \
        .replace('пер.', '').replace('д.', '').replace('ул.', '') \
        .replace('пр.', '').replace('пр-т.', '').replace('пр-т', '')

    cities_by = ['Мінск', 'Брэст', 'Гродна', 'Віцебск', 'Гомель', 'Магілёў']
    cities_ru = ['Минск', 'Брест', 'Гродно', 'Витебск', 'Гомель', 'Могилев']

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
            datetime_parser.get_current_datetime(day_to_shift)

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


async def send_form_message(form: str, user_id: int, language: str) -> None:
    text = locales.text(language, 'continue_work') + '\n\n' + \
        locales.text(language, form)

    await bot.send_message(user_id, text)


async def show_settings(message, state):
    logger.info('Настройки - ' + str(message.from_user.username))

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)
        email = get_value(data, 'sender_email')

    text = locales.text(language, 'select_section')

    # настроим клавиатуру
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

    if email:
        keyboard.add(personal_info_button,
                     appeal_email_button,
                     language_settings_button)
    else:
        keyboard.add(personal_info_button, language_settings_button)

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


def get_next_form(items: list, current: Any) -> Any:
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


async def show_personal_info(message: types.Message, state: FSMContext):
    logger.info('Показ инфы отправителя - ' + str(message.from_user.username))

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

    # настроим клавиатуру
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


async def get_language_text_and_keyboard(data):
    language = await get_ui_lang(data=data)

    ui_lang_name = locales.text(language, 'lang' + language)
    letter_lang_name = locales.text(language,
                                    'lang' + get_value(data, 'letter_lang'))

    text = locales.text(language, 'current_ui_lang') +\
        ' <b>{}</b>.'.format(ui_lang_name) + '\n' +\
        '\n' +\
        locales.text(language, 'current_letter_lang') +\
        ' <b>{}</b>.'.format(letter_lang_name)

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    change_ui_language_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_ui_language_button'),
        callback_data='/change_ui_language')

    change_letter_language_button = types.InlineKeyboardButton(
        text=locales.text(language, 'change_letter_language_button'),
        callback_data='/change_letter_language')

    keyboard.add(change_ui_language_button, change_letter_language_button)

    return text, keyboard


async def user_banned(*args):
    bot_id = (await bot.get_me()).id

    async with dp.current_state(chat=bot_id, user=bot_id).proxy() as data:
        for name in args:
            if name in get_value(data, 'banned_users'):
                return True, get_value(data, 'banned_users')[name]

    return False, ''


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
        violation_address = f'{city}, {entered_address}'
        language = await get_ui_lang(data=data)

    await set_violation_address(user_id, violation_address, state)
    await print_violation_address_info(state, user_id)
    await ask_for_violation_time(user_id, language)


@dp.callback_query_handler(
    lambda call: call.data == '/user_city_as_violations',
    state=Form.short_address_check)
async def choose_users_city(call, state: FSMContext):
    await bot.answer_callback_query(call.id)
    logger.info('Нажал на кнопку своего города как города нарушения - ' +
                str(call.from_user.username))

    async with state.proxy() as data:
        user_city = get_value(data, 'sender_city')

    await set_violation_city(state, call.message.chat.id, user_city)


@dp.callback_query_handler(lambda call: call.data == '/confirm_button',
                           state=Form.short_address_check)
async def address_is_full_click(call, state: FSMContext):
    await bot.answer_callback_query(call.id)
    logger.info('Подтвердил, что адрес с городом - ' +
                str(call.from_user.username))

    language = await get_ui_lang(state)
    await print_violation_address_info(state, call.message.chat.id)
    await ask_for_violation_time(call.message.chat.id, language)


@dp.callback_query_handler(lambda call: call.data == '/settings',
                           state='*')
async def settings_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки настроек - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await show_settings(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/personal_info',
                           state='*')
async def personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки показа личных данных - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await show_personal_info(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/enter_password',
                           state='*')
async def personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода email пароля - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await invite_to_enter_email_password(call.message.chat.id, state)


@dp.callback_query_handler(lambda call: call.data == '/delete_password',
                           state='*')
async def personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки удаления email пароля - ' +
                str(call.from_user.username))

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
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        await send_language_info(call.message.chat.id, data)


@dp.callback_query_handler(lambda call: call.data == '/appeal_email',
                           state='*')
async def language_settings_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки пороля емаила - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        await send_appeal_email_info(call.message.chat.id, data)


@dp.callback_query_handler(lambda call: call.data == '/enter_personal_info',
                           state='*')
async def enter_personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода личных данных - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await ask_for_sender_info(call.message,
                              state,
                              Form.sender_first_name.state)


@dp.callback_query_handler(lambda call: call.data == '/verify_email',
                           state='*')
async def verify_email_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки верификации почты - ' +
                str(call.from_user.username))

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
        text = locales.text(language, 'enter_secret_code') + '\n' +\
            locales.text(language, 'spam_folder')

        async with state.proxy() as data:
            data['secret_code'] = secret_code

        await Form.email_verifying.set()

    await bot.send_message(call.message.chat.id, text)


@dp.callback_query_handler(lambda call: call.data == '/reset',
                           state='*')
async def delete_personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки удаления личных данных - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await cmd_reset(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/forward_button',
                           state=SENDER_INFO)
async def sender_info_forward(call, state: FSMContext):
    current_form = await state.get_state()

    logger.info(f'Кнопка вперед {current_form} - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    next_form = get_next_form(SENDER_INFO, current_form)
    await ask_for_sender_info(call.message, state, next_form, edit=True)


@dp.callback_query_handler(lambda call: call.data == '/back_button',
                           state=SENDER_INFO)
async def sender_info_forward(call, state: FSMContext):
    current_form = await state.get_state()

    logger.info(f'Кнопка назад {current_form} - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    next_form = get_next_form(REVERSED_SENDER_INFO, current_form)
    await ask_for_sender_info(call.message, state, next_form, edit=True)


@dp.callback_query_handler(lambda call: call.data == '/change_ui_language',
                           state='*')
async def change_language_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки смены языка бота - ' +
                str(call.from_user.username))

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


@dp.callback_query_handler(lambda call: call.data == '/change_letter_language',
                           state='*')
async def change_language_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки смены языка писем - ' +
                str(call.from_user.username))

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
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await show_private_info_summary(call.message.chat.id, state)


@dp.callback_query_handler(lambda call: call.data == '/current_time',
                           state=Form.violation_datetime)
async def current_time_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода текущего времени - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    current_time = get_str_current_time()

    message = await bot.send_message(call.message.chat.id, current_time)
    await catch_violation_time(message, state)


@dp.callback_query_handler(lambda call: call.data == '/yesterday',
                           state=Form.violation_datetime)
async def yesterday_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки вчера - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    await react_to_time_button(call.message.chat.id,
                               call.message.message_id,
                               state,
                               day_to_shift=-1)


@dp.callback_query_handler(lambda call: call.data == '/before_yesterday',
                           state=Form.violation_datetime)
async def before_yesterday_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки позавчера - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    await react_to_time_button(call.message.chat.id,
                               call.message.message_id,
                               state,
                               day_to_shift=-2)


@dp.callback_query_handler(lambda call: call.data == '/enter_violation_addr',
                           state=Form.violation_datetime)
async def violation_address_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода адреса нарушения - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        await ask_for_violation_address(call.message.chat.id, data)


@dp.callback_query_handler(lambda call: call.data == '/enter_recipient',
                           state=Form.violation_datetime)
async def recipient_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода реципиента - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    # этот текст не менять или менять по всему файлу
    text = locales.text(language, 'choose_recipient')

    # настроим клавиатуру
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
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    # настроим клавиатуру
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
    logger.info('Выбрал реципиента - ' + str(call.from_user.username))

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
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

        # зададим сразу пустое примечание
        set_default(data, 'violation_caption')

    text = locales.text(language, Form.vehicle_number.state) + '\n' +\
        '\n' +\
        locales.text(language, f'{Form.vehicle_number.state}_example')

    # настроим клавиатуру
    async with state.proxy() as data:
        keyboard = await get_cancel_keyboard(data)

    await bot.send_message(call.message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.vehicle_number.set()


@dp.callback_query_handler(lambda call: call.data == '/add_caption',
                           state=[Form.sending_approvement])
async def add_caption_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода примечания - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        # зададим сразу пустое примечание
        set_default(data, 'violation_caption')
        language = await get_ui_lang(data=data)

    await states_stack.add(call.message.chat.id)
    text = locales.text(language, Form.caption.state)

    # настроим клавиатуру
    async with state.proxy() as data:
        keyboard = await get_cancel_keyboard(data)

    await bot.send_message(call.message.chat.id, text, reply_markup=keyboard)
    await Form.caption.set()


@dp.callback_query_handler(lambda call: call.data == '/answer_feedback',
                           state='*')
async def answer_feedback_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ответа на фидбэк - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await states_stack.add(call.message.chat.id)

    async with state.proxy() as data:

        # сохраняем адресата
        data['feedback_post'] = call.message.text

        language = await get_ui_lang(data=data)
        text = locales.text(language, Form.feedback_answering.state)

        # настроим клавиатуру
        keyboard = await get_cancel_keyboard(data)

    await bot.send_message(call.message.chat.id,
                           text,
                           reply_markup=keyboard,
                           reply_to_message_id=call.message.message_id)

    await Form.feedback_answering.set()


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.violation_photo,
                                  Form.vehicle_number,
                                  Form.violation_datetime,
                                  Form.violation_address,
                                  Form.sending_approvement,
                                  Form.recipient,
                                  Form.short_address_check])
async def cancel_violation_input(call, state: FSMContext):
    logger.info('Отмена, возврат в рабочий режим - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

        delete_prepared_violation(data)

    await Form.operational_mode.set()
    await send_form_message(Form.operational_mode.state,
                            call.message.chat.id,
                            language)


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.feedback,
                                  Form.feedback_answering,
                                  Form.caption,
                                  Form.email_password])
async def cancel_input(call, state: FSMContext):
    logger.info('Отмена, возврат в предыдущий режим - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await pop_saved_state(call.message.chat.id, call.message.from_user.id)


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.entering_captcha])
async def cancel_captcha_input(call, state: FSMContext):
    logger.info('Отмена, возврат в предыдущий режим - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:

        await http_rabbit.send_cancel(
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
    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    text = locales.text(language, 'letter_sending_in_progress')

    await bot.send_message(call.message.chat.id, text)


@dp.callback_query_handler(lambda call: call.data == '/approve_sending',
                           state=Form.operational_mode)
async def send_appeal_again(call, state: FSMContext):
    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    text = locales.text(language, 'send_appeal_again')

    # настроим клавиатуру
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
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await Form.entering_captcha.set()

    language = await get_ui_lang(state)

    if await invalid_credentials(state):
        text = locales.text(language, 'need_personal_info')

        logger.info('Обращение не отправлено, не введены личные данные - ' +
                    str(call.from_user.username))

        await bot.send_message(call.message.chat.id, text)

        async with state.proxy() as data:
            delete_prepared_violation(data)
            # appeal_id saved to retry sending when credentials will be filled
            it_is_reply, data['appeal_id'] = \
                get_original_appeal_id(call.message)

    elif not await verified_email(state):
        logger.info('Обращение не отправлено, email не подтвержден - ' +
                    str(call.from_user.username))

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
                str(call.from_user.username))

    it_is_reply, appeal_id = get_original_appeal_id(call.message)
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


@dp.callback_query_handler(state='*')
async def reject_button_click(call, state: FSMContext):
    logger.info('Беспорядочно кликает на кнопки - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    language = await get_ui_lang(state)

    text = locales.text(language, 'irrelevant_action')

    await bot.send_message(call.message.chat.id, text)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
    """
    Conversation's entry point
    """
    logger.info('Старт работы бота - ' + str(message.from_user.username))

    language = await get_ui_lang(state)
    text = locales.text(language, 'greeting')

    await bot.send_message(message.chat.id,
                           text)

    await Form.initial.set()
    await invite_to_fill_credentials(message.chat.id, state)


@dp.message_handler(commands=['settings'], state='*')
async def show_settings_command(message: types.Message, state: FSMContext):
    logger.info('Показ настроек команда - ' + str(message.from_user.username))
    await show_settings(message, state)


@dp.message_handler(commands=['banlist'], state='*')
async def banlist_user_command(message: types.Message):
    if message.chat.id != config.ADMIN_ID:
        return

    logger.info('Банлист - ' + str(message.from_user.username))

    bot_id = (await bot.get_me()).id

    async with dp.current_state(chat=bot_id, user=bot_id).proxy() as data:
        text = str(get_value(data, 'banned_users'))
        await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=['unban'], state='*')
async def unban_user_command(message: types.Message, state: FSMContext):
    if message.chat.id != config.ADMIN_ID:
        return

    language = await get_ui_lang(state)
    logger.info('Забанил человека - ' + str(message.from_user.username))

    user = message.text.replace('/unban', '', 1).strip()

    if not user:
        text = locales.text(language, 'banned_name_expected')
        await bot.send_message(message.chat.id, text)
        return

    bot_id = (await bot.get_me()).id

    async with dp.current_state(chat=bot_id, user=bot_id).proxy() as data:
        data['banned_users'].pop(user, None)
        text = user + ' ' + locales.text(language, 'unbanned_succesfully')

    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=['ban'], state='*')
async def ban_user_command(message: types.Message, state: FSMContext):
    if message.chat.id != config.ADMIN_ID:
        return

    language = await get_ui_lang(state)
    logger.info('Забанил человека - ' + str(message.from_user.username))

    try:
        user, caption = message.text.replace('/ban ', '', 1).split(' ', 1)
    except ValueError:
        text = locales.text(language, 'name_and_caption_expected')
        await bot.send_message(message.chat.id, text)
        return

    bot_id = (await bot.get_me()).id

    async with dp.current_state(chat=bot_id, user=bot_id).proxy() as data:
        banned_users = get_value(data, 'banned_users')
        banned_users[user] = caption
        data['banned_users'] = banned_users

        text = user + ' ' + locales.text(language, 'banned_succesfully')

    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=['reset'], state='*')
async def cmd_reset(message: types.Message, state: FSMContext):
    logger.info('Сброс бота - ' + str(message.from_user.username))
    language = await get_ui_lang(state)

    await state.finish()
    await Form.initial.set()

    text = locales.text(language, 'reset') + ' ¯\\_(ツ)_/¯'
    await bot.send_message(message.chat.id, text)
    await invite_to_fill_credentials(message.chat.id, state)


@dp.message_handler(commands=['help'], state='*')
async def cmd_help(message: types.Message, state: FSMContext):
    logger.info('Вызов помощи - ' + str(message.from_user.username))

    language = await get_ui_lang(state)

    text = locales.text(language, 'manual_help') + '\n' +\
        '\n' +\
        locales.text(language, 'feedback_help')

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    privacy_policy = types.InlineKeyboardButton(
        text=locales.text(language, 'privacy_policy_button'),
        url='https://telegra.ph/Politika-konfidencialnosti-01-09')

    letter_template = types.InlineKeyboardButton(
        text=locales.text(language, 'letter_template_button'),
        url='https://docs.google.com/document/d/' +
            '11kigeRPEdqbYcMcFVmg1lv66Fy-eOyf5i1PIQpSqcII/edit?usp=sharing')

    changelog = types.InlineKeyboardButton(
        text='Changelog',
        url='https://github.com/dziaineka/parkun-bot/blob/master/README.md')

    keyboard.add(privacy_policy, letter_template, changelog)

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML',
                           disable_web_page_preview=True)


@dp.message_handler(commands=['feedback'], state='*')
async def write_feedback(message: types.Message, state: FSMContext):
    logger.info('Хочет написать фидбэк - ' + str(message.from_user.username))

    async with state.proxy() as data:
        current_state = await state.get_state()
        language = await get_ui_lang(data=data)
        text = locales.text(language, Form.feedback.state)
        keyboard = await get_cancel_keyboard(data)
        data_to_save = {'feedback_post': get_value(data, 'feedback_post')}

    if current_state != Form.feedback.state:
        await states_stack.add(message.chat.id, data_to_save)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)
    await Form.feedback.set()


@dp.message_handler(regexp=config.PREVIOUS_ADDRESS_REGEX,
                    state=Form.violation_address)
async def use_saved_address_command(message: types.Message, state: FSMContext):
    logger.info('Команда предыдущего адреса - ' +
                str(message.from_user.username))

    address_index = int(
        message.text.replace(config.PREVIOUS_ADDRESS_PREFIX, ''))

    async with state.proxy() as data:
        addresses = get_value(data, 'previous_violation_addresses')
        language = await get_ui_lang(data=data)

        try:
            previous_address = addresses[int(address_index)]
        except KeyError:
            logger.error('Ошибка при вводе предыдущего адреса' +
                         f'{str(message.from_user.username)}.\n' +
                         f'Адреса: {addresses}\n' +
                         f'Индекс: {address_index}')

            previous_address = message.text

    logger.info(f'Выбрался адрес: {previous_address} - ' +
                str(message.from_user.username))

    await set_violation_address(message.chat.id, previous_address, state)

    if maybe_no_city_in_address(previous_address):
        logger.info(f'Адрес без города: {previous_address} - ' +
                    str(message.from_user.username))

        await ask_about_short_address(state, message.chat.id)
    else:
        await print_violation_address_info(state, message.chat.id)
        await ask_for_violation_time(message.chat.id, language)


@dp.message_handler(state=Form.feedback)
async def catch_feedback(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод фидбэка - ' +
                str(message.from_user.username))

    language = await get_ui_lang(state)

    await bot.forward_message(
        chat_id=config.ADMIN_ID,
        from_chat_id=message.from_user.id,
        message_id=message.message_id,
        disable_notification=True)

    text = str(message.from_user.id) + ' ' + str(message.message_id)

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    give_feedback_button = types.InlineKeyboardButton(
        text=locales.text(language, 'reply_button'),
        callback_data='/answer_feedback')

    keyboard.add(give_feedback_button)

    await bot.send_message(config.ADMIN_ID, text, reply_markup=keyboard)

    text = locales.text(language, 'thanks_for_feedback')
    await bot.send_message(message.chat.id, text)
    await pop_saved_state(message.chat.id, message.from_user.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.feedback_answering)
async def catch_feedback(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ответ на фидбэк - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        feedback = get_value(data, 'feedback_post').split(' ')
        feedback_chat_id = feedback[0]
        feedback_message_id = feedback[1]

        await bot.send_message(feedback_chat_id,
                               message.text,
                               reply_to_message_id=feedback_message_id)

    await pop_saved_state(message.chat.id, message.from_user.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.email_verifying)
async def catch_secret_code(message: types.Message, state: FSMContext):
    logger.info('Ввод секретного кода - ' + str(message.from_user.username))

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

    await bot.send_message(message.chat.id, text, parse_mode='HTML')
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
    logger.info('Обрабатываем ввод имени - ' + str(message.from_user.username))
    language = await get_ui_lang(state)

    if not await check_validity(validator.first_name, message, language):
        await ask_for_sender_info(message, state, Form.sender_first_name.state)
        return

    async with state.proxy() as data:
        data['sender_first_name'] = message.text

    await ask_for_sender_info(message, state, Form.sender_patronymic.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_patronymic)
async def catch_sender_patronymic(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод отчества - ' +
                str(message.from_user.username))

    language = await get_ui_lang(state)

    if not await check_validity(validator.patronymic, message, language):
        await ask_for_sender_info(message,
                                  state,
                                  Form.sender_patronymic.state)
        return

    async with state.proxy() as data:
        data['sender_patronymic'] = message.text

    await ask_for_sender_info(message, state, Form.sender_last_name.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_last_name)
async def catch_sender_last_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод фамилии - ' +
                str(message.from_user.username))

    language = await get_ui_lang(state)

    if not await check_validity(validator.last_name, message, language):
        await ask_for_sender_info(message, state, Form.sender_last_name.state)
        return

    async with state.proxy() as data:
        data['sender_last_name'] = message.text

    await ask_for_sender_info(message, state, Form.sender_email.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_email)
async def catch_sender_email(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод email - ' + str(message.from_user.username))

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    try:
        if message.text.split('@')[1] in blocklist:
            logger.info('Временный email - ' + str(message.from_user.username))
            text = locales.text(language, 'no_temporary_email')
            await bot.send_message(message.chat.id, text)
            await ask_for_sender_info(message, state, Form.sender_email.state)

            return
    except IndexError:
        pass

    async with state.proxy() as data:
        data['sender_email'] = message.text
        data['sender_email_password'] = ''
        data['verified'] = False

    await ask_for_sender_info(message, state, Form.sender_phone.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_phone)
async def catch_sender_city(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод телефона - ' + str(message.chat.id))

    async with state.proxy() as data:
        data['sender_phone'] = message.text

    await ask_for_sender_info(message, state, Form.sender_city.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_city)
async def catch_sender_city(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод города - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    if not await check_validity(validator.city, message, language):
        await ask_for_sender_info(message, state, Form.sender_city.state)
        return

    async with state.proxy() as data:
        data['sender_city'] = message.text

    await ask_for_sender_info(message, state, Form.sender_street.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_street)
async def catch_sender_street(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод улицы - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    if not await check_validity(validator.street, message, language):
        await ask_for_sender_info(message, state, Form.sender_street.state)
        return

    async with state.proxy() as data:
        data['sender_street'] = message.text

    await ask_for_sender_info(message, state, Form.sender_block.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_house)
async def catch_sender_house(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод дома - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        language = await get_ui_lang(data=data)

    if not await check_validity(validator.building, message, language):
        await ask_for_sender_info(message, state, Form.sender_house.state)
        return

    async with state.proxy() as data:
        data['sender_house'] = message.text

    await ask_for_sender_info(message, state, Form.sender_flat.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_block)
async def catch_sender_block(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод корпуса - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        data['sender_block'] = message.text

    await ask_for_sender_info(message, state, Form.sender_house.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_flat)
async def catch_sender_flat(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод квартиры - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        data['sender_flat'] = message.text

    await ask_for_sender_info(message, state, Form.sender_zipcode.state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_zipcode)
async def catch_sender_zipcode(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод индекса - ' +
                str(message.from_user.username))
    language = await get_ui_lang(state)

    if not await check_validity(validator.zipcode, message, language):
        return

    async with state.proxy() as data:
        data['sender_zipcode'] = message.text

    await show_private_info_summary(message.chat.id, state)


@dp.message_handler(content_types=types.ContentTypes.PHOTO,
                    state=[Form.operational_mode,
                           Form.violation_photo])
async def process_violation_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку фотки нарушения - ' +
                str(message.from_user.username))

    language = await get_ui_lang(state)

    # проверим не забанен ли пользователь
    banned, reason = await user_banned(message.from_user.username,
                                       str(message.chat.id))

    if banned:
        text = locales.text(language, 'you_are_banned') + ' ' + reason

        await bot.send_message(message.chat.id, text)
        return

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

        text = locales.text(language, 'photo_or_info') + '\n' +\
            '\n' +\
            '👮🏻‍♂️' + ' ' + locales.text(language, 'photo_quality_warning')

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_violation_info = types.InlineKeyboardButton(
        text=locales.text(language, 'violation_info_button'),
        callback_data='/enter_violation_info')

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(enter_violation_info, cancel)

    await message.reply(text,
                        reply_markup=keyboard,
                        parse_mode='HTML',
                        disable_web_page_preview=True)

    await Form.violation_photo.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.vehicle_number)
async def catch_vehicle_number(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод гос. номера - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        data['violation_vehicle_number'] = prepare_registration_number(
            message.text)
        await ask_for_violation_address(message.chat.id, data)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.caption)
async def catch_vehicle_number(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод примечания - ' +
                str(message.from_user.username))

    await pop_saved_state(message.chat.id, message.from_user.id)
    await Form.sending_approvement.set()

    async with state.proxy() as data:
        data['violation_caption'] = message.text.strip()
        await approve_sending(message.chat.id, data)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.email_password)
async def catch_email_password(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод пароля email - ' +
                str(message.from_user.username))
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
                    state=Form.short_address_check)
async def catch_violation_city(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод города нарушения - ' +
                str(message.from_user.username))
    await set_violation_city(state, message.chat.id, message.text)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_address)
async def catch_violation_location(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса нарушения - ' +
                str(message.from_user.username))

    await set_violation_address(message.chat.id, message.text, state)
    language = await get_ui_lang(state)

    if maybe_no_city_in_address(message.text):
        logger.info(f'Адрес без города: {message.text} - ' +
                    str(message.from_user.username))

        await ask_about_short_address(state, message.chat.id)
    else:
        await print_violation_address_info(state, message.chat.id)
        await ask_for_violation_time(message.chat.id, language)


@dp.message_handler(content_types=types.ContentType.LOCATION,
                    state=Form.violation_address)
async def catch_gps_violation_location(message: types.Message,
                                       state: FSMContext):
    logger.info('Обрабатываем ввод локации адреса нарушения - ' +
                str(message.from_user.username))

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
        logger.info('Не распознал локацию - ' +
                    str(message.from_user.username))

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
                str(message.chat.username))

    await Form.sending_approvement.set()

    async with state.proxy() as data:
        datetime = datetime_parser.get_violation_datetime(
            get_value(data, 'violation_date'),
            message.text)

        if not datetime:
            logger.info('Неправильно ввел датовремя - ' +
                        str(message.chat.username))

            language = await get_ui_lang(data=data)
            text = locales.text(language, 'invalid_datetime')
            await bot.send_message(message.chat.id, text)
            await ask_for_violation_time(message.chat.id, language)
            return

        data['violation_datetime'] = datetime
        await approve_sending(message.chat.id, data)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.entering_captcha)
async def catch_captcha(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод капчи - ' + str(message.chat.username))

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
                str(message.from_user.username))

    language = await get_ui_lang(state)
    text = locales.text(language, 'great_expectations')

    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=Form.violation_photo)
async def reject_wrong_violation_photo_input(message: types.Message,
                                             state: FSMContext):
    language = await get_ui_lang(state)
    text = locales.text(language, 'photo_or_info')

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_violation_info = types.InlineKeyboardButton(
        text=locales.text(language, 'violation_info_button'),
        callback_data='/enter_violation_info')

    cancel = types.InlineKeyboardButton(
        text=locales.text(language, 'cancel_button'),
        callback_data='/cancel')

    keyboard.add(enter_violation_info, cancel)

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
                           Form.short_address_check])
async def reject_non_text_input(message: types.Message, state: FSMContext):
    logger.info('Посылает не текст, а что-то другое - ' +
                str(message.from_user.username))

    language = await get_ui_lang(state)
    text = locales.text(language, 'text_only')

    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=[Form.sending_approvement,
                           Form.recipient])
async def ask_for_button_press(message: types.Message, state: FSMContext):
    logger.info('Нужно нажать на кнопку - ' + str(message.from_user.username))
    language = await get_ui_lang(state)
    text = locales.text(language, 'buttons_only')
    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=None)
async def ask_for_button_press(message: types.Message, state: FSMContext):
    logger.info('Нет стейта - ' + str(message.from_user.username))
    await cmd_start(message, state)


async def startup(dispatcher: Dispatcher):
    logger.info('Старт бота.')
    logger.info('Загружаем границы регионов.')
    await locator.download_boundaries()
    logger.info('Подключаемся к очереди статусов обращений.')
    asyncio.create_task(amqp_rabbit.start(loop, status_received))
    logger.info('Подключились.')


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
