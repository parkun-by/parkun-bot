from os import getenv
from os.path import join, dirname
from dotenv import load_dotenv

# Create .env file path.
dotenv_path = join(dirname(__file__), ".env")

# Load file from the path.
load_dotenv(dotenv_path)

# telegram bot token. Get it here https://t.me/BotFather
API_TOKEN = getenv("API_TOKEN", "")
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
    FRUNZIENSKI: 'Frunzienski rajon, Minsk',
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
REDIS_HOST = getenv("REDIS_HOST", "localhost")
REDIS_PORT = getenv("REDIS_PORT", "16379")
REDIS_PASSWORD = getenv("REDIS_PASSWORD", "redis")

# bot owner's telegram id to receive feedback
ADMIN_ID = int(getenv("ADMIN_ID", "00000000"))

# yandex maps
YANDEX_MAPS_API_KEY = getenv("YANDEX_MAPS_API_KEY", "UNNECESSARY_FOR_DEV")

BASE_YANDEX_MAPS_URL = getenv("BASE_YANDEX_MAPS_URL",
                              "http://localhost:18080/yandex_maps/?")

# to post into channel bot needs to be admin there
CHANNEL = getenv("CHANNEL", "@channel_name")
TRASH_CHANNEL = getenv("TRASH_CHANNEL", "@channel_name")
RESPONSE_HASHTAG = '#ответГАИ'
RESPONSE_EXAMPLE = 'https://t.me/parkun/24390'

# email verifier url (default response 111)
MAIL_VERIFIER_URL = getenv("MAIL_VERIFIER_URL",
                           "http://localhost:18080/validate")
VERIFYING_FAIL = '42'

# Twitter
TWI_URL = getenv("TWI_URL", "twitter.com/SOME_TWITTER_ACCOUNT")

# VK
VK_URL = getenv("VK_URL", "vk.com/SOME_VK_ACCOUNT")

# RabbitMQ
RABBIT_HOST = getenv("RABBIT_HOST", "localhost")
RABBIT_HTTP_PORT = getenv("RABBIT_HTTP_PORT", "15672")
RABBIT_AMQP_PORT = getenv("RABBIT_AMQP_PORT", "5672")

RABBIT_LOGIN = getenv("RABBIT_LOGIN", "parkun_bot")
RABBIT_PASSWORD = getenv("RABBIT_PASSWORD", "parkun_bot")

RABBIT_HTTP_ADDRESS = \
    f'http://{RABBIT_LOGIN}:{RABBIT_PASSWORD}@{RABBIT_HOST}:{RABBIT_HTTP_PORT}'

RABBIT_AMQP_ADDRESS = \
    f'amqp://{RABBIT_LOGIN}:{RABBIT_PASSWORD}@{RABBIT_HOST}:{RABBIT_AMQP_PORT}'

RABBIT_EXCHANGE_MANAGING = 'managing'
RABBIT_EXCHANGE_SENDING = 'sending'
RABBIT_EXCHANGE_SHARING = 'sharing'
RABBIT_ROUTING_VIOLATION = 'violation'
RABBIT_ROUTING_APPEAL_TO_QUEUE = 'appeal_to_queue'
RABBIT_QUEUE_STATUS = 'status_to_bot'
RABBIT_QUEUE_APPEALS = 'appeal'

# sender messages types
CAPTCHA_TEXT = 'captcha_text'
CAPTCHA_URL = 'captcha_url'
APPEAL = 'appeal'
CANCEL = 'cancel'
CAPTCHA_OK = 'captcha_ok'
SENDING_CANCELLED = 'sending_cancelled'
POST_URL = 'post_url'

# status codes
OK = 'ok'
BAD_EMAIL = 'bad_email'

# Telegra.ph
TPH_ACCESS_TOKEN = getenv("TPH_ACCESS_TOKEN", "some_token")
TPH_SHORT_NAME = getenv("TPH_SHORT_NAME", "author_nickname")
TPH_AUTHOR_NAME = getenv("TPH_AUTHOR_NAME", "author_name")
TPH_AUTHOR_URL = getenv("TPH_AUTHOR_URL", "author_url")
TPH_AUTH_URL = getenv("TPH_AUTH_URL", "author_auth_url")

# Pause before task execution (in hours, 10 min default)
DEFAULT_SCHEDULER_PAUSE = float(getenv("DEFAULT_SCHEDULER_PAUSE", "0.16"))

# text styles
BOLD = 'bold'
ITALIC = 'italic'
MONO = 'mono'
STRIKE = 'strike'

# broadcaster reply messages types
VIOLATION = 'violation'
POLICE_RESPONSE = 'police_response'

# numberplates recognizer
NUMBERPLATES_RECOGNIZER_ENABLED = True

NUMBERPLATES_RECOGNIZER_URL = getenv("NUMBERPLATES_RECOGNIZER_URL",
                                     "http://localhost:5001/recognize")

# how many previos addresses should we save
ADDRESS_AMOUNT_TO_SAVE = 5

MIN_ADDRESS_LENGTH = 10
