# telegram bot token. Get it here https://t.me/BotFather
API_TOKEN = 'PUT_TOKEN_HERE'
URL_BASE = 'https://api.telegram.org/file/bot' + API_TOKEN + '/'

# violation photos count upper bound in single appeal
MAX_VIOLATION_PHOTOS = 10

# appeal language
BY = '_by'
RU = '_ru'

# SendInBlue
SIB_ACCESS_KEY = 'access_key'

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

EMAIL_TO = {
    MINSK: 'PUT_YOUR_TEST_EMAIL',
    BREST_REGION: 'PUT_YOUR_TEST_EMAIL',
    VITSEBSK_REGION: 'PUT_YOUR_TEST_EMAIL',
    HOMEL_REGION: 'PUT_YOUR_TEST_EMAIL',
    HRODNA_REGION: 'PUT_YOUR_TEST_EMAIL',
    MINSK_REGION: 'PUT_YOUR_TEST_EMAIL',
    MAHILEU_REGION: 'PUT_YOUR_TEST_EMAIL',
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
