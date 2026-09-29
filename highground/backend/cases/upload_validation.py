"""Small signature check for the upload types the project accepts."""

from pathlib import Path


EXTENSIONS = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}


def has_expected_signature(upload):
    kind = upload.content_type
    if Path(upload.name).suffix.lower() not in EXTENSIONS.get(kind, set()):
        return False
    head = upload.read(12)
    upload.seek(0)
    if kind == "application/pdf":
        return head.startswith(b"%PDF-")
    if kind == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if kind == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if kind == "image/webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False
