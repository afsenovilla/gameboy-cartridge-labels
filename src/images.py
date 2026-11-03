import os, cv2, numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

# Reads a photo, upright, whatever the system: as BGR pixels, the way every step and tool sees it. Text recognition's
# corners and the fits in fits.json are in these pixels, so the EXIF orientation is always applied. cv2.imread can't open
# a path with non-ASCII characters on Windows, so the bytes are read first; HEIC, which OpenCV can't read, goes through
# pillow-heif (it replaced macOS's sips).
register_heif_opener()


def read(path):
    """The photo at path, upright, as a BGR array; None if it can't be read."""
    try:
        data = np.fromfile(path, np.uint8)
    except OSError:
        return None
    photo = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if photo is not None:
        return photo
    try:
        with Image.open(path) as image:
            return cv2.cvtColor(np.asarray(ImageOps.exif_transpose(image).convert("RGB")), cv2.COLOR_RGB2BGR)
    except (OSError, ValueError):
        return None


def write(path, image, *params):
    """Writes an image, its format from the path's extension, also to a path with non-ASCII characters."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cv2.imencode(os.path.splitext(path)[1], image, list(params))[1].tofile(path)
