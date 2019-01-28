class PhotoItem(dict):
    def __init__(self, type, media, caption):
        dict.__init__(self, type=type, media=media, caption=caption)
