import io, os, secrets
from PIL import Image, UnidentifiedImageError
Image.MAX_IMAGE_PIXELS = 40_000_000

def save_image(file_storage, upload_dir):
    """Validate by decoding, strip all metadata (EXIF/GPS) by re-encoding, random server-chosen name."""
    raw = file_storage.read(6 * 1024 * 1024 + 1)
    if not raw or len(raw) > 6 * 1024 * 1024: raise ValueError("Image must be under 6 MB.")
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format not in ("JPEG", "PNG", "WEBP"): raise ValueError("Only JPG, PNG or WEBP images are allowed.")
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file isn't a valid image.")
    im = im.convert("RGB"); im.thumbnail((1600, 1600))
    name = secrets.token_hex(16) + ".webp"
    im.save(os.path.join(upload_dir, name), "WEBP", quality=82)
    return name
