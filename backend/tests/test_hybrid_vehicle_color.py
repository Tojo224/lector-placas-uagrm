from dataclasses import dataclass

import cv2
import numpy as np
import pytest
from app.services.vehicle_color import HybridVehicleColorAnalyzer


@dataclass
class Box:
    x1: int = 20
    y1: int = 20
    x2: int = 300
    y2: int = 190


@dataclass
class Detection:
    label: str = "car"
    confidence: float = 0.9
    bounding_box: Box = None

    def __post_init__(self):
        self.bounding_box = self.bounding_box or Box()


class Detector:
    def __init__(self, detections=None):
        self.detections = detections if detections is not None else [Detection()]

    def predict(self, image):
        return self.detections


def encoded_scene(color=(180, 70, 35)):
    image = np.full((220, 340, 3), (8, 8, 8), np.uint8)
    cv2.rectangle(image, (20, 20), (300, 190), color, -1)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def test_weak_opencv_without_trained_fallback_returns_unknown(monkeypatch):
    analyzer = HybridVehicleColorAnalyzer(Detector())
    monkeypatch.setattr(analyzer.opencv, "analyze", lambda *_: [
        {"valor": "NEGRO", "cobertura": .59, "confianza": .59}
    ])

    result = analyzer.analyze(encoded_scene(), [130, 140, 190, 165])

    assert result.color_sugerido == "DESCONOCIDO"
    assert result.color_hex is None
    assert result.metodo_color == "DESCONOCIDO"


def test_dark_background_is_not_sent_to_clip_without_associated_vehicle():
    analyzer = HybridVehicleColorAnalyzer(Detector([]))

    result = analyzer.analyze(encoded_scene((5, 5, 5)), [130, 140, 190, 165])

    assert result.color_sugerido == "DESCONOCIDO"
    assert result.metodo_color == "DESCONOCIDO"


def test_low_confidence_vehicle_box_is_rejected():
    analyzer = HybridVehicleColorAnalyzer(Detector([Detection(confidence=.20)]))

    result = analyzer.analyze(encoded_scene(), [130, 140, 190, 165])

    assert result.color_sugerido == "DESCONOCIDO"
    assert result.metodo_color == "DESCONOCIDO"


def test_confident_opencv_returns_shared_contract(monkeypatch):
    analyzer = HybridVehicleColorAnalyzer(Detector())
    monkeypatch.setattr(analyzer.opencv, "analyze", lambda *_: [
        {"valor": "BLANCO", "cobertura": .9, "confianza": .82}
    ])

    result = analyzer.analyze(encoded_scene(), [130, 140, 190, 165])

    assert result.color_sugerido == "BLANCO"
    assert result.metodo_color == "OPENCV"
