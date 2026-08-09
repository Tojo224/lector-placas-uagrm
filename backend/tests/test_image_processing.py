import io
import unittest

from app.services.image_processing import (
    ImageProcessingConfig,
    ImageProcessingError,
    ImageProcessingService,
)
from PIL import Image


def encoded(fmt="JPEG", size=(120, 80), exif=None):
    output = io.BytesIO()
    options = {"exif": exif} if exif is not None else {}
    Image.new("RGB", size, "navy").save(output, format=fmt, **options)
    return output.getvalue()


class ImageProcessingTests(unittest.TestCase):
    def setUp(self):
        self.service = ImageProcessingService()

    def test_jpeg_to_webp(self):
        result = self.service.process(encoded("JPEG"), "VEHICLE_REGISTRATION")
        self.assertEqual(result.format, "webp")
        self.assertEqual(Image.open(io.BytesIO(result.content)).format, "WEBP")

    def test_png_to_webp(self):
        result = self.service.process(encoded("PNG"), "ACCESS_ENTRY")
        self.assertEqual(Image.open(io.BytesIO(result.content)).format, "WEBP")

    def test_user_is_center_cropped(self):
        result = self.service.process(encoded(size=(900, 600)), "USER_PROFILE")
        self.assertEqual((result.width, result.height), (512, 512))

    def test_vehicle_is_not_upscaled(self):
        result = self.service.process(encoded(size=(300, 200)), "VEHICLE_REGISTRATION")
        self.assertEqual((result.width, result.height), (300, 200))

    def test_access_dimension_is_limited(self):
        service = ImageProcessingService(ImageProcessingConfig(access_max_dimension=100))
        result = service.process(encoded(size=(300, 150)), "ACCESS_EXIT")
        self.assertEqual((result.width, result.height), (100, 50))

    def test_exif_is_removed_and_orientation_is_applied(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private metadata"
        result = self.service.process(
            encoded(size=(40, 20), exif=exif), "VEHICLE_REGISTRATION"
        )
        saved = Image.open(io.BytesIO(result.content))
        self.assertEqual(saved.size, (20, 40))
        self.assertEqual(len(saved.getexif()), 0)

    def test_corrupt_file_is_rejected(self):
        with self.assertRaises(ImageProcessingError):
            self.service.process(b"not-an-image", "ACCESS_ENTRY")

    def test_oversized_file_is_rejected_before_decode(self):
        service = ImageProcessingService(ImageProcessingConfig(max_upload_bytes=4))
        with self.assertRaises(ImageProcessingError):
            service.process(b"12345", "ACCESS_ENTRY")


if __name__ == "__main__":
    unittest.main()
