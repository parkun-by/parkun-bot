# telegram bot token. Get it here https://t.me/BotFather
API_TOKEN = 'PUT_TOKEN_HERE'
URL_BASE = 'https://api.telegram.org/file/bot' + API_TOKEN + '/'

# violation photos count upper bound in single appeal
MAX_VIOLATION_PHOTOS = 10

# appeal language
BY = '_by'
RU = '_ru'
LANGUAGES = [BY, RU]

# bot config
PREVIOUS_ADDRESS_PREFIX = '/saved_'
PREVIOUS_ADDRESS_REGEX = r'\/saved_\d+'
APPEAL_STORAGE_LIMIT = 3
TEMP_FILES_PATH = '/tmp/temp_files_parkun'

# regionalization
MINSK = 'minsk'

CENTRALNY = 'centralny'
SAVIECKI = 'saviecki'
PIERSAMAJSKI = 'piersamajski'
PARTYZANSKI = 'partyzanski'
ZAVODSKI = 'zavodski'
LENINSKI = 'leninski'
KASTRYCNICKI = 'kastrycnicki'
MASKOUSKI = 'maskouski'
FRUNZIENSKI = 'frunzienski'

BREST_REGION = 'brest_region'
VITSEBSK_REGION = 'vitsebsk_region'
HOMEL_REGION = 'homel_region'
HRODNA_REGION = 'hrodna_region'
MINSK_REGION = 'minsk_region'
MAHILEU_REGION = 'mahileu_region'

REGIONS = {
    MINSK: {CENTRALNY: {},
            FRUNZIENSKI: {},
            KASTRYCNICKI: {},
            LENINSKI: {},
            MASKOUSKI: {},
            PARTYZANSKI: {},
            PIERSAMAJSKI: {},
            SAVIECKI: {},
            ZAVODSKI: {}, },
    BREST_REGION: {},
    VITSEBSK_REGION: {},
    HOMEL_REGION: {},
    HRODNA_REGION: {},
    MINSK_REGION: {},
    MAHILEU_REGION: {},
}

OSM_REGIONS = {
    CENTRALNY: 'Centralny raion, Minsk',
    FRUNZIENSKI: 'Frunzienski paion, Minsk',
    KASTRYCNICKI: 'Kastryčnicki raion, Minsk',
    LENINSKI: 'Leninski raion, Minsk',
    MASKOUSKI: 'Maskoŭski raion, Minsk',
    PARTYZANSKI: 'Partyzanski raion, Minsk',
    PIERSAMAJSKI: 'Pieršamajski Rajon, Minsk',
    SAVIECKI: 'Saviecki raion, Minsk',
    ZAVODSKI: 'Zavodski raion, Minsk',
    MINSK: 'Minsk, Belarus',
    BREST_REGION: 'Brest Region, Belarus',
    VITSEBSK_REGION: 'Vitsebsk Region, Belarus',
    HOMEL_REGION: 'Homel Region, Belarus',
    HRODNA_REGION: 'Hrodna Region, Belarus',
    MINSK_REGION: 'Minsk Region, Belarus',
    MAHILEU_REGION: 'Mahilyow Region, Belarus',
}

# redis
REDIS_HOST = 'localhost'
REDIS_PORT = '16379'
REDIS_PASSWORD = 'redis'

# bot owner's telegram id to receive feedback
ADMIN_ID = 00000000

# yandex maps
YANDEX_MAPS_API_KEY = 'UNNECESSARY_FOR_DEV'
BASE_YANDEX_MAPS_URL = 'http://localhost:18080/yandex_maps/?'
ADDRESS_FAIL = 'no_address'

# to post into channel bot needs to be admin there
CHANNEL = '@channel_name'
TRASH_CHANNEL = '@channel_name'
RESPONSE_HASHTAG = '#ответГАИ'
RESPONSE_EXAMPLE = 'https://t.me/parkun/24390'

# email verifier url
MAIL_VERIFIER_URL = 'http://localhost:18080/validate'  # response 111
VERIFYING_FAIL = '42'

# Twitter
TWI_URL = 'twitter.com/SOME_TWITTER_ACCOUNT'

# VK
VK_URL = 'vk.com/SOME_VK_ACCOUNT'

# RabbitMQ
RABBIT_HOST = 'localhost'
RABBIT_HTTP_PORT = '15672'
RABBIT_AMQP_PORT = '5672'

RABBIT_LOGIN = 'parkun_bot'
RABBIT_PASSWORD = 'parkun_bot'

RABBIT_HTTP_ADDRESS = \
    f'http://{RABBIT_LOGIN}:{RABBIT_PASSWORD}@{RABBIT_HOST}:{RABBIT_HTTP_PORT}'

RABBIT_AMQP_ADDRESS = \
    f'amqp://{RABBIT_LOGIN}:{RABBIT_PASSWORD}@{RABBIT_HOST}:{RABBIT_AMQP_PORT}'

RABBIT_EXCHANGE_MANAGING = 'managing'
RABBIT_EXCHANGE_SENDING = 'sending'
RABBIT_EXCHANGE_SHARING = 'sharing'
RABBIT_ROUTING_VIOLATION = 'violation'
RABBIT_ROUTING_APPEAL_TO_QUEUE = 'appeal_to_queue'
RABBIT_QUEUE_STATUS = 'sending_status'
RABBIT_QUEUE_APPEALS = 'appeal'

# sender messages types
CAPTCHA_TEXT = 'captcha_text'
CAPTCHA_URL = 'captcha_url'
CAPTCHA_FAIL = 'captcha_fail'
GET_CAPTCHA = 'get_captcha'
APPEAL = 'appeal'
CANCEL = 'cancel'
CAPTCHA_OK = 'captcha_ok'
SENDING_CANCELLED = 'sending_cancelled'
FREE_WORKER = 'free_worker'
BUSY_WORKER = 'busy_worker'

# status codes
OK = 'ok'
FAIL = 'fail'
WRONG_INPUT = 'wrong_input'

# Telegra.ph
TPH_ACCESS_TOKEN = "put_token_here"

TPH_SHORT_NAME = "author_nickname"
TPH_AUTHOR_NAME = "author_name"
TPH_AUTHOR_URL = "author_url"

TPH_AUTH_URL = "author_auth_url"
