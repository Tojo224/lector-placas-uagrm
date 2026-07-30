import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from app.ai.pipeline import (
    PIPELINE_MODE,
    _SCORE_ASPECT_WEIGHT,
    _SCORE_CONFIDENCE_WEIGHT,
    _SCORE_LENGTH_WEIGHT,
    _SCORE_POSITION_WEIGHT,
    _SCORE_SIZE_WEIGHT,
    _SCORE_VALID_FORMAT_WEIGHT,
    _confidence_value,
    analyze_plate,
)
from app.config.settings import settings


def image_bytes(width=320, height=180):
    image = np.full((height, width, 3), 180, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("No se pudo crear la imagen de prueba.")
    return encoded.tobytes()


class MockFastALPR:
    def __init__(self, predictions):
        self.predictions = predictions

    def predict(self, image):
        return self.predictions


def prediction(text="1234ABC", ocr_confidence=0.92, detector_confidence=0.90):
    return SimpleNamespace(
        detection=SimpleNamespace(
            confidence=detector_confidence,
            bounding_box=SimpleNamespace(x1=20, y1=70, x2=230, y2=150),
        ),
        ocr=SimpleNamespace(text=text, confidence=ocr_confidence),
    )


class OCRPipelineTests(unittest.TestCase):
    def test_scoring_weights_are_named_and_sum_to_one(self):
        self.assertAlmostEqual(
            sum(
                (
                    _SCORE_VALID_FORMAT_WEIGHT,
                    _SCORE_CONFIDENCE_WEIGHT,
                    _SCORE_LENGTH_WEIGHT,
                    _SCORE_ASPECT_WEIGHT,
                    _SCORE_SIZE_WEIGHT,
                    _SCORE_POSITION_WEIGHT,
                )
            ),
            1.0,
        )

    def test_explicit_zero_confidence_is_preserved(self):
        self.assertEqual(_confidence_value(0.0), 0.0)

    def test_empty_image(self):
        result = analyze_plate(b"", plate_engine=MockFastALPR([]))
        self.assertEqual(result["error_code"], "empty_image")

    def test_invalid_image(self):
        result = analyze_plate(b"not-an-image", plate_engine=MockFastALPR([]))
        self.assertEqual(result["error_code"], "invalid_image")

    def test_ocr_unavailable(self):
        result = analyze_plate(image_bytes())
        self.assertEqual(result["http_status"], 503)

    def test_fast_plate_ocr_detects_valid_plate(self):
        with patch.object(settings, "OCR_CONFIDENCE_THRESHOLD", 0.40):
            result = analyze_plate(image_bytes(), plate_engine=MockFastALPR([prediction()]))
        self.assertEqual(result["status"], "DETECTED")
        self.assertEqual(result["normalized_plate"], "1234ABC")
        self.assertEqual(result["detection_backend"], PIPELINE_MODE)

    def test_no_prediction_requires_manual_review(self):
        result = analyze_plate(image_bytes(), plate_engine=MockFastALPR([]))
        self.assertEqual(result["status"], "LOW_CONFIDENCE")
        self.assertTrue(result["requires_manual_review"])

    def test_low_confidence_is_not_confirmed(self):
        with patch.object(settings, "OCR_CONFIDENCE_THRESHOLD", 0.55):
            result = analyze_plate(
                image_bytes(),
                realtime=True,
                plate_engine=MockFastALPR([prediction(ocr_confidence=0.20)]),
            )
        self.assertEqual(result["status"], "LOW_CONFIDENCE")
        self.assertIsNone(result["normalized_plate"])


if __name__ == "__main__":
    unittest.main()
