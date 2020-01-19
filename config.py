# telegram bot token. Get it here https://t.me/BotFather
API_TOKEN = 'PUT_TOKEN_HERE'
URL_BASE = 'https://api.telegram.org/file/bot' + API_TOKEN + '/'

# violation photos count upper bound in single appeal
MAX_VIOLATION_PHOTOS = 10

# appeal language
BY = '_by'
RU = '_ru'

# regionalization
MINSK = 'minsk'
BREST_REGION = 'brest_region'
VITSEBSK_REGION = 'vitsebsk_region'
HOMEL_REGION = 'homel_region'
HRODNA_REGION = 'hrodna_region'
MINSK_REGION = 'minsk_region'
MAHILEU_REGION = 'mahileu_region'

REGIONS = [
    MINSK,
    BREST_REGION,
    VITSEBSK_REGION,
    HOMEL_REGION,
    HRODNA_REGION,
    MINSK_REGION,
    MAHILEU_REGION,
]

DEPARTMENT_NAMES = {
    MINSK: 'ГУВД Мингорисполкома',
    BREST_REGION: 'УВД Брестского облисполкома',
    VITSEBSK_REGION: 'УВД Витебского облисполкома',
    HOMEL_REGION: 'УВД Гомельского облисполкома',
    HRODNA_REGION: 'УВД Гродненского облисполкома',
    MINSK_REGION: 'УВД Минского облисполкома',
    MAHILEU_REGION: 'УВД Могилевского облисполкома',
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

# email verifier url
MAIL_VERIFIER_URL = 'http://localhost:18080/validate'  # response 111
VERIFYING_FAIL = '42'

# Twitter twitter unnecessary for general development
CONSUMER_KEY = 'consumer_key'
CONSUMER_SECRET = 'consumer_secret'
ACCESS_TOKEN = 'access_token'
ACCESS_TOKEN_SECRET = 'access_token_secret'
MAX_TWI_CHARACTERS = 280
MAX_TWI_PHOTOS = 4
TWI_URL = 'twitter.com/SOME_TWITTER_ACCOUNT'

# RabbitMQ
RABBIT_LOGIN = 'parkun_bot'
RABBIT_PASSWORD = 'parkun_bot'

RABBIT_HTTP_ADDRESS = \
    f'http://{RABBIT_LOGIN}:{RABBIT_PASSWORD}@localhost:15672'

RABBIT_AMQP_ADDRESS = f'amqp://{RABBIT_LOGIN}:{RABBIT_PASSWORD}@localhost:5672'
RABBIT_EXCHANGE_MANAGING = 'managing'
RABBIT_EXCHANGE_SENDING = 'sending'
RABBIT_EXCHANGE_SHARING = 'sharing'
RABBIT_ROUTING_VIOLATION = 'violation'
RABBIT_ROUTING_APPEAL_TO_QUEUE = 'appeal_to_queue'
RABBIT_QUEUE_STATUS = 'sending_status'

# sender messages types
CAPTCHA_TEXT = 'captcha_text'
CAPTCHA_URL = 'captcha_url'
CAPTCHA_FAIL = 'captcha_fail'
GET_CAPTCHA = 'get_captcha'
APPEAL = 'appeal'
CANCEL = 'cancel'
CAPTCHA_OK = 'captcha_ok'
FREE_WORKER = 'free_worker'
BUSY_WORKER = 'busy_worker'

# status codes
OK = 'ok'
FAIL = 'fail'
WRONG_INPUT = 'wrong_input'
