import cv2
import numpy as np

from app.ai.vehicle_color import detect_vehicle_color


def _image_bytes(bgr: tuple[int, int, int]) -> bytes:
    image = np.full((300, 500, 3), (30, 30, 30), dtype=np.uint8)
    image[60:230, 70:430] = bgr
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def test_detects_red_vehicle_body_above_plate():
    result = detect_vehicle_color(_image_bytes((20, 20, 220)), [210, 205, 290, 230])
    assert result.color == "Rojo"
    assert result.confidence >= 0.7


def test_detects_blue_vehicle_body_above_plate():
    result = detect_vehicle_color(_image_bytes((220, 40, 30)), [210, 205, 290, 230])
    assert result.color == "Azul"
    assert result.confidence >= 0.7


def test_detects_white_vehicle_body_above_plate():
    result = detect_vehicle_color(_image_bytes((235, 235, 235)), [210, 205, 290, 230])
    assert result.color == "Blanco"


def test_detects_black_vehicle_body_above_plate():
    result = detect_vehicle_color(_image_bytes((35, 35, 35)), [210, 205, 290, 230])
    assert result.color == "Negro"


def test_invalid_image_returns_no_suggestion():
    result = detect_vehicle_color(b"not-an-image", None)
    assert result.color is None
    assert result.confidence == 0.0
