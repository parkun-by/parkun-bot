import asyncio
import logging

from os import path
from datetime import datetime
from aiogram import Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.utils import exceptions, executor

import config
from states import Form
from mailer import Mailer


mailer = Mailer(config.SIB_ACCESS_KEY)


def setup_logging():
    # create logger
    logger = logging.getLogger('memstrual_log')
    logger.setLevel(logging.DEBUG)

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
    logger.addHandler(ch)

    return logger

loop = asyncio.get_event_loop()
bot = Bot(token=config.API_TOKEN, loop=loop)

storage = RedisStorage2(host=config.REDIS_HOST,
                        port=config.REDIS_PORT)

dp = Dispatcher(bot, storage=storage)

logger = setup_logging()

CREDENTIALS = ['sender_name',
               'sender_email',
               'sender_adress',
               'sender_phone']


async def invite_to_fill_credentials(chat_id):
    message = 'Первым делом нужно заполнить информацию о себе ' +\
        '(ФИО, адрес, телефон, которые будут в письме в ГАИ) ' +\
        'выполнив команду /setup_sender.'

    await bot.send_message(chat_id, message)


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
    text = 'Перед тем, как мы отправим письмо на ящик ' + config.EMAIL_TO +\
        ' (и копию вам на ' + data['sender_email'] +\
        ') прошу проверить основную информацию ' +\
        'и нажать кнопку "Отправить письмо", если все ок:' + '\n' +\
        '\n' +\
        'Обращающийся:' + '\n' +\
        'Имя: ' + data['sender_name'] + '\n' +\
        'Email: ' + data['sender_email'] + '\n' +\
        'Адрес: ' + data['sender_adress'] + '\n' +\
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
    text = text.replace('__АДРЕСЗАЯВИТЕЛЯ__', data['sender_adress'])
    text = text.replace('__ТЕЛЕФОНЗАЯВИТЕЛЯ__', data['sender_phone'])

    return text


async def approve_sending(chat_id, state):
    async with state.proxy() as data:
        text = await compose_summary(data)

    # Configure ReplyKeyboardMarkup
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Отправить письмо", "Отмена")

    await bot.send_message(chat_id, text, reply_markup=markup)


async def prepare_mail_parameters(state):
    async with state.proxy() as data:
        parameters = {}

        parameters['to'] = {config.EMAIL_TO: config.NAME_TO}
        parameters['bcc'] = {data['sender_email']: data['sender_name']}
        parameters['from'] = [data['sender_email'], data['sender_name']]
        parameters['html'] = await compose_letter_body(data)
        parameters['attachment'] = data['attachments']

        return parameters


def get_str_current_time():
    current_time = datetime.now()

    day = str(current_time.day).rjust(2, '0')
    month = str(current_time.month).rjust(2, '0')
    year = str(current_time.year)
    hour = str(current_time.hour).rjust(2, '0')
    minute = str(current_time.minute).rjust(2, '0')

    formated_current_time = '{}.{}.{} {}:{}'.format(day,
                                                    month,
                                                    year,
                                                    hour,
                                                    minute)

    return formated_current_time


async def invalid_credentials(state):
    async with state.proxy() as data:
        for user_info in CREDENTIALS:
            if (user_info not in data) or (data[user_info] == ''):
                return True

    return False


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
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

    text = 'Введите свое ФИО (при повторном вводе можно пропустить этот ' +\
        'шаг отправив точку "."). ' + '\n' +\
        '\n' +\
        'Пример: Зенон Станиславович Позняк.'

    await bot.send_message(message.chat.id, text)
    await Form.sender_name.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_name)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод ФИО пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        if message.text != '.':
            data['sender_name'] = message.text

    text = 'Введите свой email, с него будут отправляться письма в ГАИ (' +\
        'при повторном вводе можно пропустить этот ' +\
        'шаг отправив точку "."). ' + '\n' +\
        '\n' +\
        'Пример: example@example.com'

    await bot.send_message(message.chat.id, text)
    await Form.sender_email.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_email)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод email пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        if message.text != '.':
            data['sender_email'] = message.text

    text = 'Введите свой адрес проживания, на него придет ответ из ГАИ (' +\
        'при повторном вводе можно пропустить этот ' +\
        'шаг отправив точку "."). ' + '\n' +\
        '\n' +\
        'Пример: г. Минск, пр. Независимости, д. 17, кв. 25.'

    await bot.send_message(message.chat.id, text)
    await Form.sender_adress.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_adress)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        if message.text != '.':
            data['sender_adress'] = message.text

    text = 'Введите свой номер телефона (' +\
        'при повторном вводе можно пропустить этот ' +\
        'шаг отправив точку "."). ' + '\n' +\
        '\n' +\
        'Пример: +375221111111.'

    await bot.send_message(message.chat.id, text)
    await Form.sender_phone.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.sender_phone)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод телефона пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        if message.text != '.':
            data['sender_phone'] = message.text

    if await invalid_credentials(state):
        text = 'Без ввода полной информации о себе вы не сможете отправить ' +\
               'обращение в ГАИ. Зато уже можете загрузить фото и ' +\
               'посмотреть, как все работает.'
    else:
        text = 'Все готово, можно слать фото нарушителей парковки.'

    await bot.send_message(message.chat.id, text)
    await Form.operational_mode.set()


@dp.message_handler(commands=['reset'], state='*')
async def cmd_reset(message: types.Message, state: FSMContext):
    logger.info('Сброс бота у пользователя ' + str(message.from_user.id))

    await state.finish()
    await Form.initial.set()

    text = 'Стер себе память, настраивай заново теперь ¯\_(ツ)_/¯'
    await bot.send_message(message.chat.id, text)
    await invite_to_fill_credentials(message.chat.id)


@dp.message_handler(content_types=types.ContentTypes.PHOTO,
                    state=Form.operational_mode)
async def process_operational_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку фотки нарушения. ' +
                str(message.from_user.id))

    # Добавляем фотку наилучшего качества(последнюю в массиве) в список
    # прикрепления в письме
    await add_photo_to_attachments(message.photo[-1], state)

    text = 'Добавьте еще одно фото или перейдите ко вводу информации ' +\
        'о нарушении по кнопке "Гос. номер, адрес, время".'

    # Configure ReplyKeyboardMarkup
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Гос. номер, адрес, время", "Отмена")

    await message.reply(text, reply_markup=markup)


@dp.message_handler(lambda message: message.text == 'Отмена',
                    content_types=types.ContentTypes.TEXT,
                    state=[Form.operational_mode,
                           Form.vehicle_number,
                           Form.violation_datetime,
                           Form.violation_location,
                           Form.violation_sending])
async def cancel_violation_input(message: types.Message, state: FSMContext):
    logger.info('Отмена отправки нарушения от пользователя ' +
                str(message.from_user.id))

    await delete_prepared_violation(state)

    text = 'Отправка нарушения отменена.'
    await message.reply(text, reply_markup=types.ReplyKeyboardRemove())
    await Form.operational_mode.set()


@dp.message_handler(lambda message: message.text == 'Гос. номер, адрес, время',
                    content_types=types.ContentTypes.TEXT,
                    state=Form.operational_mode)
async def cancel_violation_input(message: types.Message):
    logger.info('Обрабатываем нажатие кнопки ввода инфы о нарушении ' +
                ' от пользователя ' + str(message.from_user.id))

    text = 'Введите гос. номер транспортного средства.' + '\n' +\
        '\n' +\
        'Пример: 9999 АА-9'

    # Configure ReplyKeyboardMarkup
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Отмена")

    await message.reply(text, reply_markup=markup)

    await Form.vehicle_number.set()


@dp.message_handler(lambda message: message.text == 'Отправить письмо',
                    content_types=types.ContentTypes.TEXT,
                    state=Form.violation_sending)
async def send_letter(message: types.Message, state: FSMContext):
    logger.info('Отправляем письмо в ГАИ от пользователя ' +
                str(message.from_user.id))

    if await invalid_credentials(state):
        text = 'Для отправки нарушений нужно заполнить информацию ' +\
            'о себе командой /setup_sender'
    else:
        parameters = await prepare_mail_parameters(state)

        try:
            mailer.send_mail(parameters)
            text = 'Письмо отправлено. Проверьте ящик - вам придет копия.'

            logger.info('Письмо отправлено у пользователя ' +
                        str(message.from_user.id))
        except Exception as exc:
            text = 'При отправке что-то пошло не так. Очень жаль.' + '\n' +\
                    str(exc)

            logger.error('Неудачка у пользователя ' +
                         str(message.from_user.id) + '\n' +
                         str(exc))

    await bot.send_message(message.chat.id,
                           text,
                           reply_markup=types.ReplyKeyboardRemove())

    await delete_prepared_violation(state)
    await Form.operational_mode.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.vehicle_number)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод гос. номера от пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['vehicle_number'] = message.text

    text = 'Введите адрес, где произошло нарушение.' + '\n' +\
        '\n' +\
        'Пример: г. Минск, пр. Независимости, д. 17.'

    await bot.send_message(message.chat.id, text)
    await Form.violation_location.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_location)
async def catch_sender_name(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод адреса нарушения от пользователя ' +
                str(message.from_user.id))

    async with state.proxy() as data:
        data['violation_location'] = message.text

    current_time = get_str_current_time()

    text = 'Введите дату и время нарушения. Ввести текущее время ' +\
        'можно кнопкой снизу.' + '\n' +\
        '\n' +\
        'Пример: ' + current_time + '.'

    # Configure ReplyKeyboardMarkup
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add(current_time, "Отмена")

    await bot.send_message(message.chat.id, text, reply_markup=markup)
    await Form.violation_datetime.set()


@dp.message_handler(content_types=types.ContentType.TEXT,
                    state=Form.violation_datetime)
async def catch_sender_name(message: types.Message, state: FSMContext):
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
                    state=[Form.vehicle_number,
                           Form.violation_datetime,
                           Form.violation_location])
async def reject_wrong_input(message: types.Message):
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
