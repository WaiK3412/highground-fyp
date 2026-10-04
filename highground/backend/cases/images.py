"""Rewrite uploaded photo pixels without identifying metadata (NFR3).

Generated names hide source filenames; rewriting removes embedded metadata.
Visible faces and house numbers still need the uploader's care and permission.
"""

import io
import uuid
import warnings
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

FORMATS = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}


class UnreadableImage(ValueError):
    """An upload cannot be safely decoded as its declared image format."""


def generated_name(upload, extension=None):
    return f"{uuid.uuid4().hex}{extension or Path(upload.name).suffix.lower()}"


def clean_photo(upload):
    pillow_format, extension = FORMATS[upload.content_type]
    try:
        # Refuse the warning threshold too, before decoding large pixel buffers.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as opened:
                if opened.format != pillow_format:
                    raise UnreadableImage(f"{upload.name} is not a valid {pillow_format} image.")
                # Apply orientation before discarding EXIF so phone photos stay upright.
                image = ImageOps.exif_transpose(opened)
                if pillow_format == "JPEG" and image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                elif image.mode == "P" or "transparency" in image.info:
                    image = image.convert("RGBA")
                # PNG can inherit EXIF/ICC from info even without save options.
                # Transparency above is converted to pixels before clearing it.
                image.info.clear()
                out = io.BytesIO()
                image.save(out, format=pillow_format)
    except (
        UnidentifiedImageError, OSError, SyntaxError,
        Image.DecompressionBombError, Image.DecompressionBombWarning,
    ) as exc:
        raise UnreadableImage(
            f"{upload.name} could not be read safely. Choose another JPEG, PNG or WebP photo."
        ) from exc
    finally:
        upload.seek(0)
    return ContentFile(out.getvalue(), name=generated_name(upload, extension))
