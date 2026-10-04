"""NFR3: photos retain upright pixels, without hidden metadata or source names."""

import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image, PngImagePlugin

from cases.images import UnreadableImage, clean_photo, generated_name
from .photo_helpers import GPS_IFD, jpeg_with_gps, photo_upload


class CleanPhotoTests(SimpleTestCase):
    def test_gps_and_all_exif_are_removed(self):
        cleaned = clean_photo(jpeg_with_gps())
        with Image.open(io.BytesIO(cleaned.read())) as result:
            self.assertEqual(dict(result.getexif()), {})

    def test_filename_is_generated(self):
        self.assertRegex(clean_photo(jpeg_with_gps()).name, r"^[0-9a-f]{32}\.jpg$")

    def test_generated_pdf_name_keeps_only_the_extension(self):
        upload = SimpleUploadedFile("aisyah_address.PDF", b"%PDF-1.4")
        self.assertRegex(generated_name(upload), r"^[0-9a-f]{32}\.pdf$")

    def test_orientation_is_applied_before_the_tag_is_dropped(self):
        cleaned = clean_photo(jpeg_with_gps(orientation=6))
        with Image.open(io.BytesIO(cleaned.read())) as result:
            self.assertEqual(result.size, (20, 40))
            self.assertEqual(dict(result.getexif()), {})

    def test_png_and_webp_keep_their_format(self):
        for fmt, ext in (("PNG", ".png"), ("WEBP", ".webp")):
            with self.subTest(fmt=fmt):
                cleaned = clean_photo(photo_upload(f"a{ext}", fmt))
                self.assertTrue(cleaned.name.endswith(ext))
                with Image.open(io.BytesIO(cleaned.read())) as result:
                    self.assertEqual(result.format, fmt)

    def test_png_exif_text_and_profile_are_not_kept(self):
        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", "Lot 77 Jalan Kadok")
        exif = Image.Exif()
        exif[GPS_IFD] = {1: "N", 2: (6.0, 7.0, 8.0)}
        cleaned = clean_photo(photo_upload(
            "a.png", "PNG", pnginfo=info, exif=exif, icc_profile=b"private profile",
        ))
        with Image.open(io.BytesIO(cleaned.read())) as result:
            self.assertEqual(dict(result.getexif()), {})
            self.assertNotIn("Comment", result.info)
            self.assertNotIn("icc_profile", result.info)

    def test_webp_exif_xmp_and_profile_are_not_kept(self):
        exif = Image.Exif()
        exif[GPS_IFD] = {1: "N", 2: (6.0, 7.0, 8.0)}
        cleaned = clean_photo(photo_upload(
            "a.webp", "WEBP", exif=exif, xmp=b"private address", icc_profile=b"private profile",
        ))
        with Image.open(io.BytesIO(cleaned.read())) as result:
            self.assertEqual(dict(result.getexif()), {})
            self.assertNotIn("xmp", result.info)
            self.assertNotIn("icc_profile", result.info)

    def test_png_transparency_is_preserved(self):
        out = io.BytesIO()
        Image.new("RGB", (3, 3), (200, 30, 30)).save(
            out, format="PNG", transparency=(200, 30, 30),
        )
        cleaned = clean_photo(SimpleUploadedFile("a.png", out.getvalue(), content_type="image/png"))
        with Image.open(io.BytesIO(cleaned.read())) as result:
            self.assertEqual(result.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_undecodable_image_is_refused(self):
        fake = SimpleUploadedFile("x.jpg", b"\xff\xd8\xffnot really a jpeg", content_type="image/jpeg")
        with self.assertRaises(UnreadableImage):
            clean_photo(fake)

    def test_truncated_pixels_are_refused(self):
        upload = jpeg_with_gps()
        upload = SimpleUploadedFile("x.jpg", upload.read()[:-40], content_type="image/jpeg")
        with self.assertRaises(UnreadableImage):
            clean_photo(upload)

    def test_format_mismatch_is_refused(self):
        upload = photo_upload("x.png", "PNG")
        upload.content_type = "image/jpeg"
        with self.assertRaises(UnreadableImage):
            clean_photo(upload)

    def test_decompression_warning_and_error_are_refused(self):
        for pixel_limit in (60, 20):
            with self.subTest(pixel_limit=pixel_limit), patch.object(Image, "MAX_IMAGE_PIXELS", pixel_limit):
                with self.assertRaises(UnreadableImage):
                    clean_photo(photo_upload())

    def test_upload_is_rewound_after_cleaning(self):
        upload = jpeg_with_gps()
        clean_photo(upload)
        self.assertEqual(upload.tell(), 0)
