import asyncio
import logging
import pytz
from datetime import datetime
from os import path

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.utils import executor

import config
from geocoder import Geocoder
from mailer import Mailer
from states import Form

mailer = Mailer(config.SIB_ACCESS_KEY)
geocoder = Geocoder()


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
        'отправив команду /setup_sender. Введенная информация сохранится ' +\
        'для упрощения ввода нарушений. Очистить информацию о себе можно ' +\
        'командой /reset.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    setup_sender_button = types.InlineKeyboardButton(
        text='Ввести информацию о себе',
        callback_data='/setup_sender')

    keyboard.add(setup_sender_button)

    await bot.send_message(chat_id,
                           message,
                           reply_markup=keyboard)


async def add_photo_to_attachments(photo, state):
    file = await bot.get_file(photo['file_id'])
    image_url = config.URL_BASE + file.file_path

    async with state.proxy() as data:
        try:
            attachments = data['attachments']  # такого ключа может не быть
        except KeyError:
            attachments = []

        attachments.append(image_url)
        data['attachments'] = attachments


async def delete_prepared_violation(state):
    async with state.proxy() as data:
        data['attachments'] = []
        data['vehicle_number'] = ''
        data['violation_location'] = ''
        data['violation_datetime'] = ''


async def set_default_sender_info(state):
    async with state.proxy() as data:
        for user_info in CREDENTIALS:
            if user_info not in data:
                data[user_info] = ''


async def compose_summary(data):
    text = 'Перед тем, как отправить обращение на ящик ' + config.EMAIL_TO +\
        ' (и копию вам на ' + data['sender_email'] +\
        ') прошу проверить основную информацию ' +\
        'и нажать кнопку "Отправить письмо", если все ок:' + '\n' +\
        '\n' +\
        'Обращающийся:' + '\n' +\
        'Имя: ' + data['sender_name'] + '\n' +\
        'Email: ' + data['sender_email'] + '\n' +\
        'Адрес: ' + data['sender_address'] + '\n' +\
        'Телефон: ' + data['sender_phone'] + '\n' +\
        '\n' +\
        'Нарушитель: ' + '\n' +\
        'Гос. номер транспортного средства: ' +\
        data['vehicle_number'] + '\n' +\
        'Место нарушения (адрес): ' + data['violation_location'] + '\n' +\
        'Дата и время нарушения: ' + data['violation_datetime']

    return text


async def compose_letter_body(data):
    template = path.join('letters', 'minsk.html')

    with open(template, 'r') as file:
        text = file.read()

    text = text.replace('__ГОСНОМЕРТС__', data['vehicle_number'])
    text = text.replace('__МЕСТОНАРУШЕНИЯ__', data['violation_location'])
    text = text.replace('__ДАТАИВРЕМЯ__', data['violation_datetime'])
    text = text.replace('__ИМЯЗАЯВИТЕЛЯ__', data['sender_name'])
    text = text.replace('__АДРЕСЗАЯВИТЕЛЯ__', data['sender_address'])
    text = text.replace('__ТЕЛЕФОНЗАЯВИТЕЛЯ__', data['sender_phone'])

    return text


async def approve_sending(chat_id, state):
    async with state.proxy() as data:
        text = await compose_summary(data)

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    approve_sending_button = types.InlineKeyboardButton(
        text='Отправить письмо',
        callback_data='/approve_sending')

    cancel = types.InlineKeyboardButton(
        text='Отмена',
        callback_data='/cancel')

    keyboard.add(approve_sending_button, cancel)

    await bot.send_message(chat_id, text, reply_markup=keyboard)


async def prepare_mail_parameters(state):
    async with state.proxy() as data:
        parameters = {'to': {config.EMAIL_TO: config.NAME_TO},
                      'bcc': {data['sender_email']: data['sender_name']},
                      'from': [data['sender_email'], data['sender_name']],
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


def get_cancel_keyboard():
    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=1)

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
        'существующий email командой /setup_sender.'

    if invalid_email_msg in str(exception):
        return invalid_email_humanized

    return str(exception)


async def ask_for_user_address(chat_id):
    text = 'Введите свой адрес проживания, ' +\
        'на него придет ответ из ГАИ.' + '\n' +\
        'Можно отправить локацию и бот попробует подобрать адрес.' + '\n' +\
        '\n' +\
        'Пример: г. Минск, пр. Независимости, д. 17, кв. 25.'

    keyboard = get_skip_keyboard()

    await bot.send_message(chat_id, text, reply_markup=keyboard)
    await Form.sender_address.set()


async def ask_for_user_email(chat_id):
    text = 'Введите свой email, с него будут ' +\
        'отправляться письма в ГАИ.' + '\n' +\
        'С несуществующего адреса письмо не отправится.' + '\n' +\
        '\n' +\
        'Пример: example@example.com'

    keyboard = get_skip_keyboard()

    await bot.send_message(chat_id, text, reply_markup=keyboard)
    await Form.sender_email.set()


async def ask_for_user_phone(chat_id):
    text = 'Введите свой номер телефона (необязательно).' + '\n' +\
        '\n' +\
        'Пример: +375221111111.'

    keyboard = get_skip_keyboard()

    await bot.send_message(chat_id, text, reply_markup=keyboard)
    await Form.sender_phone.set()


async def show_private_info_summary(chat_id, state):
    if await invalid_credentials(state):
        text = 'Без ввода полной информации о себе вы не сможете отправить ' +\
               'обращение в ГАИ. Зато уже можете загрузить фото и ' +\
               'посмотреть, как все работает.'
    else:
        text = 'Все готово, можно слать фото нарушителей парковки.'

    await bot.send_message(chat_id, text)
    await Form.operational_mode.set()


async def ask_for_violation_address(chat_id):
    text = 'Введите адрес, где произошло нарушение.' + '\n' +\
        'Можно отправить локацию и бот попробует подобрать адрес.' + '\n' +\
        '\n' +\
        'Пример: г. Минск, пр. Независимости, д. 17.'

    # настроим клавиатуру
    keyboard = get_cancel_keyboard()

    await bot.send_message(chat_id, text, reply_markup=keyboard)
    await Form.violation_location.set()


@dp.callback_query_handler(lambda call: call.data == '/setup_sender',
                           state='*')
async def setup_sender_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода личных данных - ' +
                str(call.from_user.id))

    await bot.answer_callback_query(call.id)
    await setup_sender(call.message, state)


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_name)
async def skip_name_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода ФИО - ' +
                str(call.from_user.id))

    await bot.answer_callback_query(call.id)
    await ask_for_user_email(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_email)
async def skip_email_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода email - ' +
                str(call.from_user.id))

    await bot.answer_callback_query(call.id)
    await ask_for_user_address(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_address)
async def skip_address_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода адреса - ' +
                str(call.from_user.id))

    await bot.answer_callback_query(call.id)
    await ask_for_user_phone(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/skip',
                           state=Form.sender_phone)
async def skip_phone_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки пропуска ввода телефона - ' +
                str(call.from_user.id))

    await bot.answer_callback_query(call.id)
    await show_private_info_summary(call.message.chat.id, state)


@dp.callback_query_handler(lambda call: call.data == '/current_time',
                           state=Form.violation_datetime)
async def current_time_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода текущего времени - ' +
                str(call.from_user.id))

    current_time = get_str_current_time()

    message = await bot.send_message(call.message.chat.id, current_time)
    await catch_violation_time(message, state)


@dp.callback_query_handler(lambda call: call.data == '/enter_sender_address',
                           state=Form.sender_phone)
async def sender_address_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода своего адреса - ' +
                str(call.from_user.id))

    await bot.answer_callback_query(call.id)
    await ask_for_user_address(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/enter_violation_addr',
                           state=Form.violation_datetime)
async def violation_address_click(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки ввода адреса нарушения - ' +
                str(call.from_user.id))

    await bot.answer_callback_query(call.id)
    await ask_for_violation_address(call.message.chat.id)


@dp.callback_query_handler(lambda call: call.data == '/enter_violation_info',
                           state=Form.violation_photo)
async def enter_violation_info_click(call):
    logger.info('Обрабатываем нажатие кнопки ввода инфы о нарушении ' +
                ' от пользователя ' + str(call.from_user.id))

    text = 'Введите гос. номер транспортного средства.' + '\n' +\
        '\n' +\
        'Пример: 9999 АА-9'

    # настроим клавиатуру
    keyboard = get_cancel_keyboard()

    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, text, reply_markup=keyboard)
    await Form.vehicle_number.set()


@dp.callback_query_handler(lambda call: call.data == '/cancel',
                           state=[Form.violation_photo,
                                  Form.vehicle_number,
                                  Form.violation_datetime,
                                  Form.violation_location,
                                  Form.violation_sending,
                                  Form.feedback])
async def cancel_violation_input(call, state: FSMContext):
    logger.info('Отмена, возврат в рабочий режим - ' +
                str(call.from_user.id))

    await delete_prepared_violation(state)

    await bot.answer_callback_query(call.id)
    text = 'Бот вернулся в режим ожидания нарушения.'
    await bot.send_message(call.message.chat.id, text)
    await Form.operational_mode.set()


@dp.callback_query_handler(lambda call: call.data == '/approve_sending',
                           state=Form.violation_sending)
async def send_letter_click(call, state: FSMContext):
    logger.info('Отправляем письмо в ГАИ от пользователя ' +
                str(call.from_user.id))

    if await invalid_credentials(state):
        text = 'Для отправки нарушений нужно заполнить информацию ' +\
            'о себе командой /setup_sender'
    else:
        parameters = await prepare_mail_parameters(state)

        try:
            mailer.send_mail(parameters)
            text = 'Письмо отправлено. Проверьте ящик - вам придет копия.'

            logger.info('Письмо отправлено у пользователя ' +
                        str(call.from_user.id))
        except Exception as exc:
            text = 'При отправке что-то пошло не так. Очень жаль.' + '\n' +\
                await humanize_message(exc)

            logger.error('Неудачка у пользователя ' +
                         str(call.from_user.id) + '\n' +
                         str(exc))

    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, text)

    await delete_prepared_violation(state)
    await Form.operational_mode.set()


@dp.callback_query_handler(state='*')
async def reject_button_click(call):
    logger.info('Беспорядочно кликает на кнопки - ' +
                str(call.from_user.id))

    text = 'Действие неактуально.'

    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, text)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    logger.info('Старт работы бота у пользователя ' +
                str(message.from_user.id))

    text = 'Привет, этот бот упрощает посылку обращения в ГАИ о нарушении ' +\
        'правил парковки. Для работы ему потребуется от вас ' +\
        'имя, адрес, email, телефон. '

    await bot.send_message(message.chat.id,
                           text)

    await Form.initial.set()
    await invite_to_fill_credentials(message.chat.id)


@dp.message_handler(commands=['setup_sender'], state='*')
async def setup_sender(message: types.Message, state: FSMContext):
    logger.info('Настройка пользователя ' + str(message.from_user.id))

    # на всякий случай удалим введенное нарушение, если решили ввести
    # свои данные в процессе ввода нарушения
    await delete_prepared_violation(state)

    await set_default_sender_info(state)

    text = 'Введите свое ФИО.' + '\n' +\
        '\n' +\
        'Пример: Зенон Станиславович Позняк.'

    keyboard = get_skip_keyboard()

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)
    await Form.sender_name.set()


@dp.message_handler(commands=['reset'], state='*')
async def cmd_reset(message: types.Message, state: FSMContext):
    logger.info('Сброс бота у пользователя ' + str(message.from_user.id))

    await state.finish()
    await Form.initial.set()

    text = 'Стер себе память ¯\_(ツ)_/¯'
    await bot.send_message(message.chat.id, text)
    await invite_to_fill_credentials(message.chat.id)


@dp.message_handler(commands=['help'], state='*')
async def cmd_help(message: types.Message):
    logger.info('Вызов помощи - ' + str(message.from_user.id))

    text = 'Можно почитать политику конфиденциальности. ' + '\n' +\
        'Можно посмотреть шаблон письма в ГАИ.' + '\n' +\
        'По команде /feedback можно спросить разработчика.' + '\n' +\
        '\n' +\
        'Больше ничего, вроде бы, нельзя. Спасибо, что пользуетесь ботом.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    privacy_policy = types.InlineKeyboardButton(
        text='Политика конфиденциальности',
        url='https://telegra.ph/Politika-konfidencialnosti-01-09')

    letter_template = types.InlineKeyboardButton(
        text='Шаблон письма',
        url='https://docs.google.com/document/d/' +
            '11kigeRPEdqbYcMcFVmg1lv66Fy-eOyf5i1PIQpSqcII/edit?usp=sharing')

    keyboard.add(privacy_policy, letter_template)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)


@dp.message_handler(commands=['feedback'], state='*')
async def write_feedback(message: types.Message, state: FSMContext):
    logger.info('Хочет написать фидбэк - ' + str(message.from_user.id))

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
                str(message.from_user.id))

    await bot.forward_message(
        chat_id=config.ADMIN_ID,
        from_chat_id=message.from_user.id,
        message_id=message.message_id,
        disable_notification=True)

    text = 'Спасибо за отзыв! Можно продолжить работу с того же места.'
    await bot.send_message(message.chat.id, text)

    async with state.proxy() as data:
        saved_state = data['saved_state']
        await state.set_state(saved_state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_name)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод ФИО пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['sender_name'] = message.text

    await ask_for_user_email(message.chat.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_email)
async def catch_sender_email(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод email пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['sender_email'] = message.text

    await ask_for_user_address(message.chat.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_address)
async def catch_sender_address(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['sender_address'] = message.text

    await ask_for_user_phone(message.chat.id)


@dp.message_handler(content_types=types.ContentType.LOCATION,
                    state=Form.sender_address)
async def catch_gps_sender_address(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса по локации - ' +
                str(message.from_user.id))

    coordinates = (str(message.location.longitude) + ', ' +
                   str(message.location.latitude))

    address = await geocoder.get_address(coordinates)

    if address is None:
        logger.info('Не распознал локацию - ' +
                    str(message.from_user.id))

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
    logger.info('Обрабатываем ввод телефона пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['sender_phone'] = message.text

    await show_private_info_summary(message.chat.id, state)


@dp.message_handler(content_types=types.ContentTypes.PHOTO,
                    state=[Form.operational_mode,
                           Form.violation_photo])
async def process_violation_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку фотки нарушения. ' +
                str(message.from_user.id))

    # Добавляем фотку наилучшего качества(последнюю в массиве) в список
    # прикрепления в письме
    await add_photo_to_attachments(message.photo[-1], state)

    text = 'Добавьте еще одно фото или перейдите ко вводу информации ' +\
        'о нарушении по кнопке "Гос. номер, адрес, время".'

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
    await Form.violation_photo.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.vehicle_number)
async def catch_vehicle_number(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод гос. номера от пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['vehicle_number'] = message.text

    await ask_for_violation_address(message.chat.id)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_location)
async def catch_violation_location(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса нарушения от пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['violation_location'] = message.text

    current_time = get_str_current_time()

    text = 'Введите дату и время нарушения. Ввести текущее время ' +\
        'можно кнопкой снизу.' + '\n' +\
        '\n' +\
        'Пример: ' + current_time + '.'

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    current_time_button = types.InlineKeyboardButton(
        text='Текущее время',
        callback_data='/current_time')

    cancel = types.InlineKeyboardButton(
        text='Отмена',
        callback_data='/cancel')

    keyboard.add(current_time_button, cancel)

    await bot.send_message(message.chat.id, text, reply_markup=keyboard)
    await Form.violation_datetime.set()


@dp.message_handler(content_types=types.ContentType.LOCATION,
                    state=Form.violation_location)
async def catch_gps_violation_location(message: types.Message,
                                       state: FSMContext):
    logger.info('Обрабатываем ввод локации адреса нарушения - ' +
                str(message.from_user.id))

    coordinates = (str(message.location.longitude) + ', ' +
                   str(message.location.latitude))

    address = await geocoder.get_address(coordinates)

    if address is None:
        logger.info('Не распознал локацию - ' +
                    str(message.from_user.id))

        text = 'Не удалось определить адрес. Введите, пожалуйста, руками.'
        await bot.send_message(message.chat.id, text)
        return

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enter_sender_address = types.InlineKeyboardButton(
        text='Изменить адрес',
        callback_data='/enter_violation_addr')

    keyboard.add(enter_sender_address)

    bot_message = await bot.send_message(message.chat.id,
                                         address,
                                         reply_markup=keyboard)

    await catch_violation_location(bot_message, state)


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_datetime)
async def catch_violation_time(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод даты и времени нарушения от пользователя ' +
                str(message.from_user.id))

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
