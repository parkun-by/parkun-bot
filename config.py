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
REDIS_PASSWORD = ''

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
RABBIT_ADDRESS = 'amqp://parkun_bot:parkun_bot@127.0.0.1/'
RABBIT_EXCHANGE_APPEAL = 'appeal'
RABBIT_EXCHANGE_SHARING = 'sharing'
