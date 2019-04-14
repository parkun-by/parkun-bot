# bot
API_TOKEN = 'PUT_TOKEN_HERE'
URL_BASE = 'https://api.telegram.org/file/bot' + API_TOKEN + '/'

# letter language
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
    MINSK: 'pismo_guvd_minsk@mia.by',
    BREST_REGION: 'uvdbrest@brest.by',
    VITSEBSK_REGION: 'ozgs@uvd.vitebsk.gov.by',
    HOMEL_REGION: 'uvd@mail.gomel.by',
    HRODNA_REGION: 'uvd@mail.grodno.by',
    MINSK_REGION: 'priemnaja@uvd-mo.gov.by',
    MAHILEU_REGION: 'uvd@mogilev.by',
}

# redis
REDIS_HOST = 'localhost'
REDIS_PORT = '6379'
REDIS_PASSWORD = ''

# admin
ADMIN_ID = 00000000

# yandex maps
YANDEX_MAPS_API_KEY = 'PUT_TOKEN_HERE'
BASE_YANDEX_MAPS_URL = 'https://geocode-maps.yandex.ru/1.x/?'
ADDRESS_FAIL = 'no_address'

# channel
CHANNEL = '@channel_name'

# verifier
MAIL_VERIFIER_URL = 'PUT_VERIFIER_URL'
VERIFYING_FAIL = '42'

# Twitter
CONSUMER_KEY = 'consumer_key'
CONSUMER_SECRET = 'consumer_secret'
ACCESS_TOKEN = 'access_token'
ACCESS_TOKEN_SECRET = 'access_token_secret'
MAX_TWI_CHARACTERS = 280
MAX_TWI_PHOTOS = 4
TWI_URL = 'twitter.com/SOME_TWITTER_ACCOUNT'
