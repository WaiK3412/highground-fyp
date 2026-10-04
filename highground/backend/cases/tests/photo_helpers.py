"""Synthetic, decodable photo fixtures; never read household uploads."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

GPS_IFD = 0x8825
ORIENTATION = 0x0112


def jpeg_with_gps(name="siti_house.jpg", orientation=None, size=(40, 20)):
    exif = Image.Exif()
    exif[GPS_IFD] = {1: "N", 2: (6.0, 7.0, 8.0), 3: "E", 4: (102.0, 14.0, 5.0)}
    if orientation:
        exif[ORIENTATION] = orientation
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, format="JPEG", exif=exif)
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/jpeg")


def photo_upload(name="work.jpg", fmt="JPEG", size=(10, 10), **save_options):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, format=fmt, **save_options)
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name, out.getvalue(), content_type=mime)
