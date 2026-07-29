import base64
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from app.ai.pipeline import PIPELINE_MODE, analyze_plate
from app.config.settings import settings


def image_bytes(width=320, height=180):
    image = np.full((height, width, 3), 180, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("No se pudo crear la imagen de prueba.")
    return encoded.tobytes()


def ocr_item(text, confidence=0.9, x1=20, y1=80, x2=220, y2=140):
    return ([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], text, confidence)


def pipeline_settings(**overrides):
    values = {
        "OCR_ROI_X": None,
        "OCR_ROI_Y": None,
        "OCR_ROI_WIDTH": None,
        "OCR_ROI_HEIGHT": None,
        "OCR_UPSCALE_FACTOR": 1.0,
        "OCR_USE_GRAYSCALE": True,
        "OCR_USE_CONTRAST": False,
        "OCR_DENOISE": False,
        "OCR_USE_THRESHOLD": False,
        "OCR_CONFIDENCE_THRESHOLD": 0.40,
    }
    values.update(overrides)
    return patch.multiple(settings, **values)


class MockOCRReader:
    def __init__(self, results):
        self.results = results
        self.images = []
        self.kwargs = []

    def readtext(self, image, **kwargs):
        self.images.append(image)
        self.kwargs.append(kwargs)
        return self.results


class SequencedOCRReader(MockOCRReader):
    def __init__(self, result_batches):
        super().__init__([])
        self.result_batches = iter(result_batches)

    def readtext(self, image, **kwargs):
        self.images.append(image)
        self.kwargs.append(kwargs)
        return next(self.result_batches)


class OCRPipelineTests(unittest.TestCase):
    def test_empty_image(self):
        result = analyze_plate(b"", MockOCRReader([]))
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "empty_image")

    def test_invalid_image(self):
        result = analyze_plate(b"not-an-image", MockOCRReader([]))
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "invalid_image")

    def test_ocr_unavailable(self):
        result = analyze_plate(image_bytes(), None)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["http_status"], 503)

    def test_ocr_without_results_requires_manual_review(self):
        with pipeline_settings():
            result = analyze_plate(image_bytes(), MockOCRReader([]))
        self.assertEqual(result["status"], "LOW_CONFIDENCE")
        self.assertTrue(result["requires_manual_review"])

    def test_valid_plate_is_detected(self):
        reader = MockOCRReader([ocr_item("1234-ABC", 0.91)])
        with pipeline_settings():
            result = analyze_plate(image_bytes(), reader)
        self.assertEqual(result["status"], "DETECTED")
        self.assertEqual(result["normalized_plate"], "1234ABC")
        self.assertEqual(result["detection_backend"], PIPELINE_MODE)
        self.assertFalse(result["requires_manual_review"])
        self.assertEqual(reader.kwargs[0]["paragraph"], False)

    def test_realtime_preserves_resolution_for_distant_plates(self):
        reader = MockOCRReader([ocr_item("1234ABC", 0.9)])
        with pipeline_settings():
            result = analyze_plate(
                image_bytes(width=1920, height=1080), reader, realtime=True
            )
        self.assertEqual(result["status"], "DETECTED")
        self.assertEqual(max(reader.images[0].shape[:2]), 480)
        self.assertEqual(reader.kwargs[0]["mag_ratio"], 1.25)

    def test_realtime_does_not_use_fallback_when_first_pass_finds_no_text(self):
        reader = SequencedOCRReader([[], [ocr_item("1234ABC", 0.9)]])
        with pipeline_settings():
            result = analyze_plate(image_bytes(), reader, realtime=True)
        self.assertEqual(result["status"], "LOW_CONFIDENCE")
        self.assertEqual(len(reader.images), 1)

    def test_valid_plate_wins_over_higher_confidence_non_plate_text(self):
        reader = MockOCRReader(
            [
                ocr_item("ENTRADA", 0.99, 20, 20, 180, 60),
                ocr_item("5678XYZ", 0.75, 30, 100, 230, 160),
            ]
        )
        with pipeline_settings():
            result = analyze_plate(image_bytes(height=220), reader)
        self.assertEqual(result["normalized_plate"], "5678XYZ")
        self.assertEqual(result["status"], "DETECTED")

    def test_low_confidence_text_is_not_exposed_as_confirmed_plate(self):
        with pipeline_settings():
            result = analyze_plate(
                image_bytes(),
                MockOCRReader([ocr_item("1234ABC", 0.20)]),
            )
        self.assertEqual(result["status"], "LOW_CONFIDENCE")
        self.assertIsNone(result["normalized_plate"])
        self.assertTrue(result["requires_manual_review"])

    def test_two_nearby_fragments_are_combined(self):
        reader = MockOCRReader(
            [
                ocr_item("1234", 0.86, 20, 80, 110, 140),
                ocr_item("ABC", 0.88, 115, 80, 220, 140),
            ]
        )
        with pipeline_settings():
            result = analyze_plate(image_bytes(), reader)
        self.assertEqual(result["status"], "DETECTED")
        self.assertEqual(result["normalized_plate"], "1234ABC")
        self.assertEqual(result["detected_plate"], "1234 ABC")

    def test_valid_roi_is_applied_before_ocr(self):
        reader = MockOCRReader([ocr_item("1234ABC", 0.9, 10, 10, 180, 90)])
        with pipeline_settings(
            OCR_ROI_X=50,
            OCR_ROI_Y=40,
            OCR_ROI_WIDTH=100,
            OCR_ROI_HEIGHT=60,
        ):
            result = analyze_plate(image_bytes(width=300, height=200), reader)
        self.assertEqual(result["status"], "DETECTED")
        self.assertEqual(reader.images[0].shape[:2], (60, 100))

    def test_roi_outside_image_is_rejected(self):
        with pipeline_settings(
            OCR_ROI_X=250,
            OCR_ROI_Y=10,
            OCR_ROI_WIDTH=100,
            OCR_ROI_HEIGHT=60,
        ):
            result = analyze_plate(image_bytes(width=300, height=200), MockOCRReader([]))
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "invalid_roi")

    def test_annotated_image_and_crop_are_generated(self):
        with pipeline_settings():
            result = analyze_plate(
                image_bytes(),
                MockOCRReader([ocr_item("1234ABC", 0.9)]),
            )
        for field in ("annotated_image", "plate_crop"):
            self.assertTrue(result[field].startswith("data:image/jpeg;base64,"))
            payload = result[field].split(",", 1)[1]
            self.assertGreater(len(base64.b64decode(payload)), 10)


if __name__ == "__main__":
    unittest.main()
