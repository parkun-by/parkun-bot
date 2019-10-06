class PhotoItem(dict):
    def __init__(self, media_type, media, caption):
        dict.__init__(self, type=media_type, media=media, caption=caption)
