# bot
API_TOKEN = 'PUT_TOKEN_HERE'
URL_BASE = 'https://api.telegram.org/file/bot' + API_TOKEN + '/'

# letter language
BY = '_by'
RU = '_ru'

LANG_NAMES = {
    BY: 'беларуский',
    RU: 'русский'
}

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

REGIONAL_NAME = {
    MINSK: 'ГУВД Мингорисполкома',
    BREST_REGION: 'УВД Брестского облисполкома',
    VITSEBSK_REGION: 'УВД Витебского облисполкома',
    HOMEL_REGION: 'УВД Гомельского облисполкома',
    HRODNA_REGION: 'УВД Гродненского облисполкома',
    MINSK_REGION: 'УВД Минского облисполкома',
    MAHILEU_REGION: 'УВД Могилевского облисполкома',
}

EMAIL_TO = {
    MINSK: 'pismo_guvd_minsk@mia.by',
    BREST_REGION: 'uvdbrest@brest.by',
    VITSEBSK_REGION: 'ozgs@uvd.vitebsk.gov.by',
    HOMEL_REGION: 'uvd@mail.gomel.by',
    HRODNA_REGION: 'uvd@mail.grodno.by',
    MINSK_REGION: 'priemnaja@uvd-mo.gov.by',
    MAHILEU_REGION: 'uvd@mogilev.by',
}

NAME_TO = {
    MINSK: {
        BY: 'Вадзім Мікалаевіч Гаркун',
        RU: 'Вадим Николаевич Гаркун',
    },

    BREST_REGION: {
        BY: 'Міхаіл Вітальевіч Банадык',
        RU: 'Михаил Витальевич Банадык',
    },

    VITSEBSK_REGION: {
        BY: 'Міхаіл Аляксандравіч Дзядзічкін',
        RU: 'Михаил Александрович Дядичкин',
    },

    HOMEL_REGION: {
        BY: 'Андрэй Мікалаевіч Гаркуша',
        RU: 'Андрей Николаевич Гаркуша',
    },

    HRODNA_REGION: {
        BY: 'Уладзімір Мікалаевіч Назарка',
        RU: 'Владимир Николаевич Назарко',
    },

    MINSK_REGION: {
        BY: 'Мікалай Міхайлавіч Караткевіч',
        RU: 'Николай Михайлович Короткевич',
    },

    MAHILEU_REGION: {
        BY: 'Міхаіл Міхайлавіч Неўмяржыцкі',
        RU: 'Михаил Михайлович Невмержицкий',
    }
}


# redis
REDIS_HOST = 'localhost'
REDIS_PORT = '6379'
REDIS_PASSWORD = ''

# admin
ADMIN_ID = 00000000

# yandex maps
YANDEX_MAPS_API_KEY = 'PUT_TOKEN_HERE'
BASE_YANDEX_MAPS_URL = 'https://geocode-maps.yandex.ru/1.x/'

# channel
CHANNEL = '@channel_name'

# verifier
MAIL_VERIFIER_URL = 'PUT_VERIFIER_URL'
VERIFYING_FAIL = '42'
