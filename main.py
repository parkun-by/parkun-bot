import asyncio
import logging
from datetime import datetime
from os import path

import pytz
from aiogram import Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.utils import executor
from aiogram.utils.exceptions import InvalidQueryID
from disposable_email_domains import blocklist

import config
from locator import Locator
from mail_verifier import MailVerifier
from mailer import Mailer
from photoitem import PhotoItem
from states import Form
from uploader import Uploader

mailer = Mailer(config.SIB_ACCESS_KEY)
locator = Locator()
mail_verifier = MailVerifier()
uploader = Uploader()
semaphore = asyncio.Semaphore()


def setup_logging():
    # create logger
    my_logger = logging.getLogger('parkun_log')
    my_logger.setLevel(logging.DEBUG)

    # create file handler which logs even debug messages
    # fh = logging.FileHandler(config.LOG_PATH)
    # fh.setLevel(logging.DEBUG)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    # logger.addHandler(fh)
    my_logger.addHandler(ch)

    return my_logger


loop = asyncio.get_event_loop()
bot = Bot(token=config.API_TOKEN, loop=loop)

storage = RedisStorage2(host=config.REDIS_HOST,
                        port=config.REDIS_PORT)

dp = Dispatcher(bot, storage=storage)

logger = setup_logging()

CREDENTIALS = ['sender_name',
               'sender_email',
               'sender_address',
               'sender_phone']

REQUIRED_CREDENTIALS = ['sender_name',
                        'sender_email',
                        'sender_address']


async def invite_to_fill_credentials(chat_id):
    message = 'Первым делом нужно ввести информацию о себе ' +\
        '(ФИО, адрес, телефон, которые будут в письме в ГАИ) ' +\
        'отправив команду /personal_info. Введенная информация сохранится ' +\
        'для упрощения ввода нарушений. Очистить информацию о себе можно ' +\
        'командой /reset.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    personal_info_button = types.InlineKeyboardButton(
        text='Ввести информацию о себе',
        callback_data='/enter_personal_info')

    keyboard.add(personal_info_button)

    await bot.send_message(chat_id,
                           message,
                           reply_markup=keyboard)


async def invite_to_confirm_email(data, chat_id):
    message = 'Для отправки обращений нужно подтвердить email. ' +\
        'После нажатия на кнопку будет выслано письмо на <b>' +\
        data['sender_email'] + '</b> с кодом, который нужно ввести боту.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    verify_email_button = types.InlineKeyboardButton(
        text='Подтвердить email',
        callback_data='/verify_email')

    keyboard.add(verify_email_button)

    await bot.send_message(chat_id,
                           message,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def add_photo_to_attachments(photo, state):
    file = await bot.get_file(photo['file_id'])

    image_url = await uploader.get_permanent_url(
        config.URL_BASE + file.file_path)

    # потанцевально узкое место, все потоки всех пользователей будут ждать
    # пока кто-то один аппендит, если я правильно понимаю
    # нужно сделать каждому пользователю свой личный семафорчик, но я пока
    # что не знаю как
    async with semaphore, state.proxy() as data:
        if ('attachments' not in data) or ('photo_id' not in data):
            data['attachments'] = []
            data['photo_id'] = []

        data['attachments'].append(image_url)
        data['photo_id'].append(photo['file_id'])


async def delete_prepared_violation(data):
    # в этом месте сохраним адрес нарушения для использования в
    # следующем обращении
    data['previous_violation_address'] = data['violation_location']

    data['attachments'] = []
    data['photo_id'] = []
    data['vehicle_number'] = ''
    data['violation_location'] = ''
    data['violation_datetime'] = ''
    data['caption'] = ''


def set_default(data, key, value):
    if key not in data:
        data[key] = value


async def set_default_sender_info(data):
    for user_info in CREDENTIALS:
        if user_info not in data:
            data[user_info] = ''

    set_default(data, 'verified', False)
    data['secret_code'] = ''
    set_default(data, 'letter_lang', config.RU)
    set_default(data, 'recipient', config.MINSK)
    set_default(data, 'previous_violation_address', '')
    data['saved_state'] = None

    data['attachments'] = []
    data['photo_id'] = []
    data['vehicle_number'] = ''
    data['violation_location'] = ''
    data['violation_datetime'] = ''


async def compose_summary(data):
    text = 'Перед тем, как отправить обращение в <b>' +\
        config.REGIONAL_NAME[data['recipient']] + '</b> на ящик ' +\
        config.EMAIL_TO[data['recipient']] +\
        ' (и копию вам на ' + data['sender_email'] +\
        ') прошу проверить основную информацию ' +\
        'и нажать кнопку "Отправить письмо", если все ок:' + '\n' +\
        '\n' +\
        'Язык отправляемого письма: <b>' +\
        config.LANG_NAMES[data['letter_lang']] + '</b>.' +\
        '\n' +\
        '\n' +\
        'Обращающийся:' + '\n' +\
        'Имя: <b>' + data['sender_name'] + '</b>' + '\n' +\
        'Email: <b>' + data['sender_email'] + '</b>' + '\n' +\
        'Адрес: <b>' + data['sender_address'] + '</b>' + '\n' +\
        'Телефон: <b>' + data['sender_phone'] + '</b>' + '\n' +\
        '\n' +\
        'Нарушитель: ' + '\n' +\
        'Гос. номер транспортного средства: <b>' +\
        data['vehicle_number'] + '</b>' + '\n' +\
        'Место нарушения (адрес): <b>' +\
        data['violation_location'] + '</b>' + '\n' +\
        'Дата и время нарушения: <b>' +\
        data['violation_datetime'] + '</b>' + '\n' +\
        '\n' +\
        'Также нарушение будет опубликовано в канале ' + config.CHANNEL

    return text


async def get_letter_header(data):
    template = path.join('letters',
                         'footer',
                         data['recipient'] + data['letter_lang'] + '.html')

    with open(template, 'r') as file:
        text = file.read()

    return text


async def get_letter_body(data):
    template = path.join('letters', 'body' + data['letter_lang'] + '.html')

    with open(template, 'r') as file:
        text = file.read()

    text = text.replace('__ГОСНОМЕРТС__', data['vehicle_number'])
    text = text.replace('__МЕСТОНАРУШЕНИЯ__', data['violation_location'])
    text = text.replace('__ДАТАИВРЕМЯ__', data['violation_datetime'])
    text = text.replace('__ИМЯЗАЯВИТЕЛЯ__', data['sender_name'])
    text = text.replace('__АДРЕСЗАЯВИТЕЛЯ__', data['sender_address'])
    text = text.replace('__ТЕЛЕФОНЗАЯВИТЕЛЯ__', data['sender_phone'])
    text = text.replace('__ПРИМЕЧАНИЕ__', data['caption'])

    return text


async def get_letter_photos(data):
    template = path.join('letters', 'photo.html')

    with open(template, 'r') as file:
        photo_template = file.read()

    text = ''

    for photo_url in data['attachments']:
        photo = photo_template.replace('__ФОТОНАРУШЕНИЯ__', photo_url)
        text += photo

    return text


async def compose_letter_body(data):
    header = await get_letter_header(data)
    body = await get_letter_body(data)
    photos = await get_letter_photos(data)

    return header + body + photos


async def approve_sending(chat_id, state):
    caption_button_text = 'Добавить примечание'

    async with state.proxy() as data:
        text = await compose_summary(data)
        await send_photos_group_with_caption(data, chat_id)

        if data['caption']:
            caption_button_text = 'Изменить примечание'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    approve_sending_button = types.InlineKeyboardButton(
        text='Отправить письмо',
        callback_data='/approve_sending')

    cancel_button = types.InlineKeyboardButton(
        text='Отмена',
        callback_data='/cancel')

    enter_violation_info_button = types.InlineKeyboardButton(
        text='Гос. номер, адрес, время',
        callback_data='/enter_violation_info')

    add_caption_button = types.InlineKeyboardButton(
        text=caption_button_text,
        callback_data='/add_caption')

    keyboard.add(enter_violation_info_button, add_caption_button)
    keyboard.add(approve_sending_button, cancel_button)

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


def get_subject(language):
    if language == config.BY:
        return 'Зварот аб парушэнні правілаў прыпынку і стаянкі ' +\
               'транспартных сродкаў'
    else:
        return 'Обращение о нарушении правил остановки и стоянки ' +\
               'транспортных средств'


async def prepare_mail_parameters(state):
    async with state.proxy() as data:
        recipient = config.NAME_TO[data['recipient']][data['letter_lang']]

        parameters = {'to': {config.EMAIL_TO[data['recipient']]: recipient},
                      'bcc': {data['sender_email']: data['sender_name']},
                      'from': [data['sender_email'], data['sender_name']],
                      'subject': get_subject(data['letter_lang']),
                      'html': await compose_letter_body(data),
                      'attachment': data['attachments']}

        return parameters


def get_str_current_time():
    tz_minsk = pytz.timezone('Europe/Minsk')
    current_time = datetime.now(tz_minsk)

    day = str(current_time.day).rjust(2, '0')
    month = str(current_time.month).rjust(2, '0')
    year = str(current_time.year)
    hour = str(current_time.hour).rjust(2, '0')
    minute = str(current_time.minute).rjust(2, '0')

    formatted_current_time = '{}.{}.{} {}:{}'.format(day,
                                                     month,
                                                     year,
                                                     hour,
                                                     minute)

    return formatted_current_time


async def invalid_credentials(state):
    async with state.proxy() as data:
        for user_info in REQUIRED_CREDENTIALS:
            if (user_info not in data) or (data[user_info] == ''):
                return True

    return False


async def verified_email(state):
    async with state.proxy() as data:
        if 'verified' not in data:
            data['verified'] = False
            return False

        return data['verified']


def get_cancel_keyboard():
    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup()

    cancel = types.InlineKeyboardButton(
        text='Отмена',
        callback_data='/cancel')

    keyboard.add(cancel)

    return keyboard


def get_skip_keyboard():
    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    skip = types.InlineKeyboardButton(
        text='Пропустить (оставить текущее значение)',
        callback_data='/skip')

    keyboard.add(skip)

    return keyboard


async def humanize_message(exception):
    invalid_email_msg = '\'message\': "valid \'from\' email address required"'
    invalid_email_humanized = 'Для отправки письма нужно ввести свой ' +\
        'существующий email командой /personal_info.'

    if invalid_email_msg in str(exception):
        return invalid_email_humanized

    return str(exception)


async def ask_for_user_address(chat_id):
    text = 'Введите свой адрес проживания, ' +\
        'на него придет ответ из ГАИ.' + '\n' +\
        'Можно отправить локацию и бот попробует подобрать адрес.' + '\n' +\
        '\n' +\
        'Пример: <b>г. Минск, пр. Независимости, д. 17, кв. 25</b>.'

    keyboard = get_skip_keyboard()

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.sender_address.set()


async def ask_for_user_email(chat_id):
    text = 'Введите свой email, с него будут ' +\
        'отправляться письма в ГАИ.' + '\n' +\
        'С несуществующего адреса письмо не отправится.' + '\n' +\
        '\n' +\
        'Пример: <b>example@example.com</b>'

    keyboard = get_skip_keyboard()

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.sender_email.set()


async def ask_for_user_phone(chat_id):
    text = 'Введите свой номер телефона (необязательно).' + '\n' +\
        '\n' +\
        'Пример: <b>+375221111111</b>.'

    keyboard = get_skip_keyboard()

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.sender_phone.set()


async def show_private_info_summary(chat_id, state):
    if await invalid_credentials(state):
        text = 'Без ввода полной информации о себе вы не сможете отправить ' +\
               'обращение в ГАИ. Зато уже можете загрузить фото и ' +\
               'посмотреть, как все работает.'

        await bot.send_message(chat_id, text)
    elif not await verified_email(state):
        async with state.proxy() as data:
            await invite_to_confirm_email(data, chat_id)
    else:
        text = 'Все готово, можно слать фото нарушителей парковки.'
        await bot.send_message(chat_id, text)

    await Form.operational_mode.set()


async def ask_for_violation_address(chat_id, data):
    text = 'Введите адрес, где произошло нарушение.' + '\n' +\
        'Можно отправить локацию и бот попробует подобрать адрес.' + '\n' +\
        '\n' +\
        'Пример: <b>г. Минск, пр. Независимости, д. 17</b>.' + '\n' +\
        '\n'

    # настроим клавиатуру
    keyboard = get_cancel_keyboard()

    if 'previous_violation_address' in data:
        if data['previous_violation_address'] != '':
            text += 'Предыдущий: <b>' + \
                data['previous_violation_address'] + '</b>'

            use_previous_button = types.InlineKeyboardButton(
                text='Использовать предыдущий',
                callback_data='/use_previous')

            keyboard.add(use_previous_button)

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.violation_location.set()


async def send_language_info(chat_id, data):
    if 'letter_lang' not in data:
        data['letter_lang'] = config.RU

    lang_name = config.LANG_NAMES[data['letter_lang']]

    text = 'Текущий язык посылаемого обращения - ' + lang_name + '.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    change_language_button = types.InlineKeyboardButton(
        text='Изменить',
        callback_data='/change_language')

    keyboard.add(change_language_button)

    await bot.send_message(chat_id, text, reply_markup=keyboard)


async def save_recipient(region, data):
    if region is None:
        data['recipient'] = config.MINSK
    else:
        data['recipient'] = region


async def print_violation_address_info(region, address, chat_id):
    text = 'Получатель письма: <b>' + config.REGIONAL_NAME[region] +\
        '</b>.' + '\n' +\
        '\n' +\
        'Адрес нарушения: <b>' + address + '</b>'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_violation_addr_button = types.InlineKeyboardButton(
        text='Изменить адрес',
        callback_data='/enter_violation_addr')

    enter_recipient_button = types.InlineKeyboardButton(
        text='Изменить получателя',
        callback_data='/enter_recipient')

    keyboard.add(enter_violation_addr_button, enter_recipient_button)

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


async def save_violation_address(address, data):
    data['violation_location'] = address

async def ask_for_violation_time(chat_id):
    current_time = get_str_current_time()

    text = 'Введите дату и время нарушения. Ввести текущее время ' +\
        'можно кнопкой снизу.' + '\n' +\
        '\n' +\
        'Пример: <b>' + current_time + '</b>.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    current_time_button = types.InlineKeyboardButton(
        text='Текущее время',
        callback_data='/current_time')

    cancel = types.InlineKeyboardButton(
        text='Отмена',
        callback_data='/cancel')

    keyboard.add(current_time_button, cancel)

    await bot.send_message(chat_id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.violation_datetime.set()


async def send_photos_group_with_caption(data, chat_id, caption=''):
    photos_id = data['photo_id']

    photos = []

    for count, photo_id in enumerate(photos_id):
        text = ''

        # первой фотке добавим общее описание
        if count == 0:
            text = caption

        photo = PhotoItem('photo', photo_id, text)
        photos.append(photo)

    await bot.send_media_group(chat_id=chat_id, media=photos)


def prepare_registration_number(number: str):
    '''заменяем в номере все символы на киррилические'''

    kyrillic = 'ABCEHKMOPTXYІ'
    latin = 'ABCEHKMOPTXYI'

    up_number = number.upper().strip()

    for num, symbol in enumerate(latin):
        up_number = up_number.replace(symbol, kyrillic[num])

    return up_number


async def set_violation_location(chat_id, address, state):
    coordinates = await locator.get_coordinates(address)
    region = await locator.get_region(coordinates)

    async with state.proxy() as data:
        await save_violation_address(address, data)
        await save_recipient(region, data)
        region = data['recipient']

    await print_violation_address_info(region, address, chat_id)
    await ask_for_violation_time(chat_id)


async def enter_personal_info(message, state):
    logger.info('Настройка отправителя - ' + str(message.from_user.username))

    async with state.proxy() as data:
        await set_default_sender_info(data)
        await send_language_info(message.chat.id, data)

    text = 'Введите свое ФИО.' + '\n' +\
        '\n' +\
        'Пример: <b>Зенон Станиславович Позняк</b>.'

    keyboard = get_skip_keyboard()

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.sender_name.set()


@dp.callback_query_handler(lambda call: call.data == '/enter_personal_info',
                           state='*')
async def personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода личных данных - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await enter_personal_info(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/verify_email',
                           state='*')
async def verify_email_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки верификации почты - ' +
                str(call.from_user.username))

    if await verified_email(state):
        text = 'Ваш email уже подтвержден.'
        await bot.send_message(call.message.chat.id, text)
        return

    async with state.proxy() as data:
        secret_code = await mail_verifier.verify(data['sender_email'])

    if secret_code == config.VERIFYING_FAIL:
        text = 'При отправке кода произошла ошибка, попробуйте ' + '\n' +\
            'еще раз. Если стабильно не получается, то обратитесь в /feedback.'

        await Form.operational_mode.set()
    else:
        text = 'Введите код, присланный ботом вам на почту.' + '\n' +\
            'Скорее всего вы найдете его в папке "Спам".'

        async with state.proxy() as data:
            data['secret_code'] = secret_code

        await Form.email_verifying.set()

    await bot.send_message(call.message.chat.id, text)


@dp.callback_query_handler(lambda call: call.data == '/reset',
                           state='*')
async def personal_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки удаления личных данных - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await cmd_reset(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_name)
async def skip_name_click(call):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода ФИО - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await ask_for_user_email(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/use_previous',
                           state=Form.violation_location)
async def use_previous_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие предыдущий адрес - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        previous_address = data['previous_violation_address']

    await set_violation_location(call.message.chat.id,
                                 previous_address,
                                 state)


@dp.callback_query_handler(lambda call: call.data == '/change_language',
                           state=[Form.vehicle_number,
                                  Form.sender_name])
async def change_language_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки смены языка - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        if data['letter_lang'] == config.RU:
            data['letter_lang'] = config.BY
        elif data['letter_lang'] == config.BY:
            data['letter_lang'] = config.RU
        else:
            data['letter_lang'] = config.RU

        lang_name = config.LANG_NAMES[data['letter_lang']]

    text = 'Текущий язык посылаемого обращения - <b>' + lang_name + '</b>.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    change_language_button = types.InlineKeyboardButton(
        text='Изменить',
        callback_data='/change_language')

    keyboard.add(change_language_button)

    await bot.edit_message_text(text,
                                call.message.chat.id,
                                call.message.message_id,
                                reply_markup=keyboard,
                                parse_mode='HTML')


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_email)
async def skip_email_click(call):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода email - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await ask_for_user_address(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_address)
async def skip_address_click(call):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода адреса - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await ask_for_user_phone(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_phone)
async def skip_phone_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода телефона - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await show_private_info_summary(call.message.chat.id, state)


@dp.callback_query_handler(lambda call: call.data == '/current_time',
                           state=Form.violation_datetime)
async def current_time_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода текущего времени - ' +
                str(call.from_user.username))

    current_time = get_str_current_time()

    message = await bot.send_message(call.message.chat.id, current_time)
    await catch_violation_time(message, state)


@dp.callback_query_handler(lambda call: call.data == '/enter_sender_address',
                           state=Form.sender_phone)
async def sender_address_click(call):
    logger.info('Обрабатываем нажатие кнопки ввода своего адреса - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)
    await ask_for_user_address(call.message.chat.id)


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
async def recipient_click(call):
    logger.info('Обрабатываем нажатие кнопки ввода реципиента - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    # этот текст не менять или менять по всему файлу
    text = 'Выберите получателя письма:'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    for region in config.REGIONAL_NAME:
        button = types.InlineKeyboardButton(
            text=config.REGIONAL_NAME[region],
            callback_data=region)

        keyboard.add(button)

    await bot.send_message(call.message.chat.id,
                           text,
                           reply_markup=keyboard)

    await Form.recipient.set()


@dp.callback_query_handler(
    lambda call: call.message.text == 'Выберите получателя письма:',
    state=Form.recipient)
async def recipient_choosen_click(call, state: FSMContext):
    logger.info('Выбрал реципиента - ' + str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        address = data['violation_location']
        await save_recipient(call.data, data)
        region = data['recipient']

    await print_violation_address_info(region, address, call.message.chat.id)
    await ask_for_violation_time(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/enter_violation_info',
                           state=[Form.violation_photo,
                                  Form.violation_sending])
async def enter_violation_info_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода инфы о нарушении - ' +
                str(call.from_user.username))

    async with state.proxy() as data:
        await send_language_info(call.message.chat.id, data)

        # зададим сразу пустое примечание
        data['caption'] = ''

    text = 'Введите гос. номер транспортного средства.' + '\n' +\
        '\n' +\
        'Пример: <b>9999 АА-9</b>'

    # настроим клавиатуру
    keyboard = get_cancel_keyboard()

    await bot.answer_callback_query(call.id)

    await bot.send_message(call.message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')

    await Form.vehicle_number.set()


@dp.callback_query_handler(lambda call: call.data == '/add_caption',
                           state=[Form.violation_sending])
async def add_caption_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода примечания - ' +
                str(call.from_user.username))

    async with state.proxy() as data:
        # зададим сразу пустое примечание
        data['caption'] = ''

        # сохраним состояние, чтобы к нему вернуться
        current_state = await state.get_state()
        data['saved_state'] = current_state

    text = 'Введите примечание к обращению (будет вставлено в тело письма).'

    # настроим клавиатуру
    keyboard = get_cancel_keyboard()

    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, text, reply_markup=keyboard)
    await Form.caption.set()


@dp.callback_query_handler(lambda call: call.data == '/answer_feedback',
                           state='*')
async def answer_feedback_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ответа на фидбэк - ' +
                str(call.from_user.username))

    async with state.proxy() as data:
        # сохраняем текущее состояние
        current_state = await state.get_state()

        if current_state != Form.feedback_answering.state:
            data['saved_state'] = current_state

        # сохраняем адресата
        data['feedback_post'] = call.message.text

    text = 'Введите ответ на фидбэк.'

    # настроим клавиатуру
    keyboard = get_cancel_keyboard()

    await bot.answer_callback_query(call.id)

    await bot.send_message(call.message.chat.id,
                           text,
                           reply_markup=keyboard,
                           reply_to_message_id=call.message.message_id)

    await Form.feedback_answering.set()


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.violation_photo,
                                  Form.vehicle_number,
                                  Form.violation_datetime,
                                  Form.violation_location,
                                  Form.violation_sending,
                                  Form.feedback,
                                  Form.feedback_answering,
                                  Form.caption])
async def cancel_violation_input(call, state: FSMContext):
    logger.info('Отмена, возврат в рабочий режим - ' +
                str(call.from_user.username))

    await bot.answer_callback_query(call.id)

    async with state.proxy() as data:
        if 'saved_state' in data:
            if data['saved_state'] is not None:
                saved_state = data['saved_state']
                await state.set_state(saved_state)
                data['saved_state'] = None

                text = 'Продолжайте работу с места, где она была прервана.'
                await bot.send_message(call.message.chat.id, text)
                return

        await delete_prepared_violation(data)
        data['feedback_post'] = ''

    text = 'Бот вернулся в режим ожидания фотокарточки нарушения.'
    await bot.send_message(call.message.chat.id, text)
    await Form.operational_mode.set()


@dp.callback_query_handler(lambda call: call.data == '/approve_sending',
                           state=Form.violation_sending)
async def send_letter_click(call, state: FSMContext):
    logger.info('Отправляем письмо в ГАИ - ' +
                str(call.from_user.username))

    if await invalid_credentials(state):
        text = 'Для отправки нарушений в ГАИ нужно заполнить информацию ' +\
            'о себе командой /personal_info'

        logger.info('Письмо не отправлено, не введены личные данные - ' +
                    str(call.from_user.username))

        await bot.send_message(call.message.chat.id, text)
    elif not await verified_email(state):
        logger.info('Письмо не отправлено, email не подтвержден - ' +
                    str(call.from_user.username))

        async with state.proxy() as data:
            await invite_to_confirm_email(data, call.message.chat.id)
    else:
        parameters = await prepare_mail_parameters(state)

        try:
            mailer.send_mail(parameters)
            text = 'Письмо отправлено в ГАИ и в ' + config.CHANNEL + '. ' +\
                'Проверьте ящик - вам придет копия.' + '\n' +\
                'Внимание! На ящики mail.ru копия не приходит ¯ \ _ (ツ) _ / ¯.'

            logger.info('Письмо отправлено - ' + str(call.from_user.username))

            async with state.proxy() as data:
                caption = 'Дата и время: ' +\
                    data['violation_datetime'] + '\n' +\
                    'Место: ' + data['violation_location'] + '\n' +\
                    'Гос. номер: ' + data['vehicle_number']

                # в канал
                await send_photos_group_with_caption(data,
                                                     config.CHANNEL,
                                                     caption)
        except Exception as exc:
            text = 'При отправке что-то пошло не так. Очень жаль.' + '\n' +\
                await humanize_message(exc)

            logger.error('Неудачка - ' + str(call.from_user.id) + '\n' +
                         str(exc))

        await bot.send_message(call.message.chat.id, text)

    # из-за того, что письмо может отправляться долго,
    # телеграм может погасить кружочек ожидания сам, и тогда будет исключение
    try:
        await bot.answer_callback_query(call.id)
    except InvalidQueryID:
        pass

    async with state.proxy() as data:
        await delete_prepared_violation(data)

    await Form.operational_mode.set()


@dp.callback_query_handler(state='*')
async def reject_button_click(call):
    logger.info('Беспорядочно кликает на кнопки - ' +
                str(call.from_user.username))

    text = 'Действие неактуально.'

    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, text)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
    """
    Conversation's entry point
    """
    logger.info('Старт работы бота - ' + str(message.from_user.username))

    text = 'Привет, этот бот упрощает посылку обращения в ГАИ о нарушении ' +\
        'правил парковки. Для работы ему потребуется от вас ' +\
        'имя, адрес, email, телефон (по желанию). '

    await bot.send_message(message.chat.id,
                           text)

    await Form.initial.set()

    async with state.proxy() as data:
        await set_default_sender_info(data)

    await invite_to_fill_credentials(message.chat.id)


@dp.message_handler(commands=['personal_info'], state='*')
async def show_personal_info(message: types.Message, state: FSMContext):
    logger.info('Показ инфы отправителя - ' + str(message.from_user.username))

    async with state.proxy() as data:
        text = 'Личные данные:' + '\n' + '\n' +\
            'Имя: <b>' + data['sender_name'] + '</b>' + '\n' +\
            'Email: <b>' + data['sender_email'] + '</b>' + '\n' +\
            'Адрес: <b>' + data['sender_address'] + '</b>' + '\n' +\
            'Телефон: <b>' + data['sender_phone'] + '</b>' + '\n'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_personal_info_button = types.InlineKeyboardButton(
        text='Редактировать',
        callback_data='/enter_personal_info')

    delete_personal_info_button = types.InlineKeyboardButton(
        text='Удалить',
        callback_data='/reset')

    keyboard.add(enter_personal_info_button, delete_personal_info_button)

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=keyboard,
                           parse_mode='HTML')


@dp.message_handler(commands=['reset'], state='*')
async def cmd_reset(message: types.Message, state: FSMContext):
    logger.info('Сброс бота - ' + str(message.from_user.username))

    await state.finish()
    await Form.initial.set()

    text = 'Стер себе память ¯\_(ツ)_/¯'
    await bot.send_message(message.chat.id, text)

    async with state.proxy() as data:
        await set_default_sender_info(data)

    await invite_to_fill_credentials(message.chat.id)


@dp.message_handler(commands=['help'], state='*')
async def cmd_help(message: types.Message):
    logger.info('Вызов помощи - ' + str(message.from_user.username))

    text = 'После однократного заполнения личных данных, можно прикрепить ' +\
        'сразу несколько фото нарушения с телефона или отправив ' +\
        'одну за одной.' + '\n' +\
        '\n' +\
        'Бот уведомит о языке отправляемого обращения - его можно ' +\
        'изменить.' + '\n' +\
        '\n' +\
        'Адрес нарушения можно ввести руками или отправить локацию ' +\
        'с телефона. Бот по адресу подберет получателя.' + '\n' +\
        '\n' +\
        'Номер ТС и время вводится руками (время еще можно кнопкой). ' +\
        'Можно добавить фото разных нарушителей по одному адресу ' +\
        'в одно время и перечислить их гос. номера.' + '\n' +\
        '\n' +\
        'На любом шаге ввода нарушения можно нажать отмену, так что не ' +\
        'стесняйтесь потестировать бота первой попавшейся под руку ' +\
        'картинкой.' + '\n' +\
        '\n' +\
        'Перед посылкой бот попросит еще раз все проверить, там тоже можно ' +\
        'отменить отправку.' + '\n' +\
        '\n' +\
        'После отправки письма бот запостит в канал ' + config.CHANNEL + ' ' +\
        'фото, адрес, дату нарушения. Можно подписаться и наблюдать.' + '\n' +\
        '\n' +\
        'Копия письма отправляется на ваш ящик.' + '\n' +\
        'На ящик на @mail.ru копия ' +\
        'письма не доходит. Видимо, потому что присылается не с ' +\
        'родного для вашего ящика почтового сервера.' +\
        '\n' +\
        '\n' +\
        'По команде /feedback можно связаться с разработчиком.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    privacy_policy = types.InlineKeyboardButton(
        text='Политика конфиденциальности',
        url='https://telegra.ph/Politika-konfidencialnosti-01-09')

    letter_template = types.InlineKeyboardButton(
        text='Шаблон письма',
        url='https://docs.google.com/document/d/' +
            '11kigeRPEdqbYcMcFVmg1lv66Fy-eOyf5i1PIQpSqcII/edit?usp=sharing')

    changelog = types.InlineKeyboardButton(
        text='Changelog',
        url='https://github.com/dziaineka/parkun-bot/blob/master/README.md')

    keyboard.add(privacy_policy, letter_template, changelog)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)


@dp.message_handler(commands=['feedback'], state='*')
async def write_feedback(message: types.Message, state: FSMContext):
    logger.info('Хочет написать фидбэк - ' + str(message.from_user.username))

    async with state.proxy() as data:
        current_state = await state.get_state()

        if current_state != Form.feedback.state:
            data['saved_state'] = current_state

    text = 'Введите все, что вы обо мне думаете, а я передам это ' +\
        'сообщение разработчику.'

    keyboard = get_cancel_keyboard()

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)
    await Form.feedback.set()


@dp.message_handler(state=Form.feedback)
async def catch_feedback(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод фидбэка - ' +
                str(message.from_user.username))

    await bot.forward_message(
        chat_id=config.ADMIN_ID,
        from_chat_id=message.from_user.id,
        message_id=message.message_id,
        disable_notification=True)

    text = str(message.from_user.id) + ' ' + str(message.message_id)

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    give_feedback_button = types.InlineKeyboardButton(
        text='Ответить',
        callback_data='/answer_feedback')

    keyboard.add(give_feedback_button)

    await bot.send_message(config.ADMIN_ID, text, reply_markup=keyboard)

    text = 'Спасибо за отзыв! Можно продолжить работу с того же места.'
    await bot.send_message(message.chat.id, text)

    async with state.proxy() as data:
        saved_state = data['saved_state']
        await state.set_state(saved_state)
        data['saved_state'] = None


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.feedback_answering)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ответ на фидбэк - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        feedback = data['feedback_post'].split(' ')
        feedback_chat_id = feedback[0]
        feedback_message_id = feedback[1]

        await bot.send_message(feedback_chat_id,
                               message.text,
                               reply_to_message_id=feedback_message_id)

        await state.set_state(data['saved_state'])
        data['saved_state'] = None

    text = 'Можно продолжить работу с того же места.'
    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.email_verifying)
async def catch_secret_code(message: types.Message, state: FSMContext):
    logger.info('Ввод секретного кода - ' + str(message.from_user.username))

    async with state.proxy() as data:
        secret_code = data['secret_code']

    if secret_code == message.text:
        async with state.proxy() as data:
            data['verified'] = True

        text = 'Ваша почта подтверждена, можно вводить нарушения.'
    else:
        text = 'Секретный код не совпадает, попробуйте запросить ' +\
            'подтверждение еще раз (нажать на кнопку).' + '\n' +\
            'Если стабильно не получается, то обратитесь в /feedback.'

    await bot.send_message(message.chat.id, text)
    await Form.operational_mode.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_name)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод ФИО - ' + str(message.from_user.username))

    async with state.proxy() as data:
        data['sender_name'] = message.text

    await ask_for_user_email(message.chat.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_email)
async def catch_sender_email(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод email - ' + str(message.from_user.username))

    if message.text.split('@')[1] in blocklist:
        logger.info('Временный email - ' + str(message.from_user.username))
        text = 'Нужно ввести постоянный email-адрес.'
        await bot.send_message(message.chat.id, text)
        await ask_for_user_email(message.chat.id)
        return

    async with state.proxy() as data:
        data['sender_email'] = message.text
        data['verified'] = False

    await ask_for_user_address(message.chat.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_address)
async def catch_sender_address(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        data['sender_address'] = message.text

    await ask_for_user_phone(message.chat.id)


@dp.message_handler(content_types=types.ContentType.LOCATION,
                    state=Form.sender_address)
async def catch_gps_sender_address(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса по локации - ' +
                str(message.from_user.username))

    coordinates = (str(message.location.longitude) + ', ' +
                   str(message.location.latitude))

    async with state.proxy() as data:
        address = await locator.get_address(coordinates, data['letter_lang'])

    if address is None:
        logger.info('Не распознал локацию - ' +
                    str(message.from_user.username))

        text = 'Не удалось определить адрес. Введите, пожалуйста, руками.'
        await bot.send_message(message.chat.id, text)
        return

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_sender_address = types.InlineKeyboardButton(
        text='Изменить адрес',
        callback_data='/enter_sender_address')

    keyboard.add(enter_sender_address)

    bot_message = await bot.send_message(message.chat.id,
                                         address,
                                         reply_markup=keyboard)

    await catch_sender_address(bot_message, state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_phone)
async def catch_sender_phone(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод телефона - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        data['sender_phone'] = message.text

    await show_private_info_summary(message.chat.id, state)


@dp.message_handler(content_types=types.ContentTypes.PHOTO,
                    state=[Form.operational_mode,
                           Form.violation_photo])
async def process_violation_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку фотки нарушения - ' +
                str(message.from_user.username))

    if message.chat.id == 612423367:
        logger.info('КЕК БАН - ' +
                    str(message.from_user.username))
        return

    # Добавляем фотку наилучшего качества(последнюю в массиве) в список
    # прикрепления в письме
    await add_photo_to_attachments(message.photo[-1], state)

    text = 'Добавьте еще одно фото или перейдите ко вводу информации ' +\
        'о нарушении по кнопке "Гос. номер, адрес, время".' + '\n' +\
        '\n' +\
        '<b>👮🏻‍♂️ По отправленным фото должен легко определяться гос. ' +\
        'номер нарушителя и само нарушение. В ГАИ фото рассматривают ' +\
        'распечатанными на чб принтере.</b>'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_violation_info = types.InlineKeyboardButton(
        text='Гос. номер, адрес, время',
        callback_data='/enter_violation_info')

    cancel = types.InlineKeyboardButton(
        text='Отмена',
        callback_data='/cancel')

    keyboard.add(enter_violation_info, cancel)

    await message.reply(text, reply_markup=keyboard, parse_mode='HTML')
    await Form.violation_photo.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.vehicle_number)
async def catch_vehicle_number(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод гос. номера - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        data['vehicle_number'] = prepare_registration_number(message.text)
        await ask_for_violation_address(message.chat.id, data)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.caption)
async def catch_vehicle_number(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод примечания - ' +
                str(message.from_user.username))

    async with state.proxy() as data:
        data['saved_state'] = None
        data['caption'] = message.text.strip()

    await Form.violation_sending.set()
    await approve_sending(message.chat.id, state)


@dp.message_handler(content_types=types.ContentType.ANY,
                    state=Form.caption)
async def catch_vehicle_number(message: types.Message):
    logger.info('Обрабатываем ввод неправильного примечания - ' +
                str(message.from_user.username))

    text = 'Допускается ввод только текста.'
    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_location)
async def catch_violation_location(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса нарушения - ' +
                str(message.from_user.username))

    await set_violation_location(message.chat.id, message.text, state)


@dp.message_handler(content_types=types.ContentType.LOCATION,
                    state=Form.violation_location)
async def catch_gps_violation_location(message: types.Message,
                                       state: FSMContext):
    logger.info('Обрабатываем ввод локации адреса нарушения - ' +
                str(message.from_user.username))

    coordinates = [message.location.longitude, message.location.latitude]

    async with state.proxy() as data:
        address = await locator.get_address(coordinates, data['letter_lang'])
        region = await locator.get_region(coordinates)
        await save_recipient(region, data)
        region = data['recipient']

    if address is None:
        logger.info('Не распознал локацию - ' +
                    str(message.from_user.username))

        text = 'Не удалось определить адрес. Введите, пожалуйста, руками.'
        await bot.send_message(message.chat.id, text)
        return

    async with state.proxy() as data:
        await save_violation_address(address, data)

    await print_violation_address_info(region, address, message.chat.id)
    await ask_for_violation_time(message.chat.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_datetime)
async def catch_violation_time(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод даты и времени нарушения - ' +
                str(message.chat.username))

    async with state.proxy() as data:
        data['violation_datetime'] = message.text

    await Form.violation_sending.set()
    await approve_sending(message.chat.id, state)


@dp.message_handler(content_types=types.ContentTypes.ANY, state=Form.initial)
async def ignore_initial_input(message: types.Message):
    await invite_to_fill_credentials(message.chat.id)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=Form.operational_mode)
async def reject_wrong_input(message: types.Message):
    logger.info('Посылает не фотку, а что-то другое - ' +
                str(message.from_user.username))

    text = 'Я ожидаю от вас фото нарушений правил остановки и ' +\
        'стоянки транспортных средств.'

    await bot.send_message(message.chat.id, text)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=Form.violation_photo)
async def reject_wrong_violation_photo_input(message: types.Message):
    text = 'Добавьте еще одно фото или нажмите "Гос. номер, адрес, время".'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_violation_info = types.InlineKeyboardButton(
        text='Гос. номер, адрес, время',
        callback_data='/enter_violation_info')

    cancel = types.InlineKeyboardButton(
        text='Отмена',
        callback_data='/cancel')

    keyboard.add(enter_violation_info, cancel)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)


@dp.message_handler(content_types=types.ContentTypes.ANY,
                    state=[Form.vehicle_number,
                           Form.violation_datetime,
                           Form.violation_location])
async def reject_wrong_violation_data_input(message: types.Message):
    text = 'Я ожидаю от вас текстовую информацию.'

    await bot.send_message(message.chat.id, text)


async def startup(dispatcher: Dispatcher):
    logger.info('Старт бота.')

    await locator.download_boundaries()


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
