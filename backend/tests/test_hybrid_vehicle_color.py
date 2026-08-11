from dataclasses import dataclass

import cv2
import numpy as np
import pytest
from app.services.color_regressor import ColorRegressorResult
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


class Clip:
    def __init__(self, result):
        self.result = result
        self.crops = []

    def classify(self, crop):
        self.crops.append(crop.copy())
        return self.result


def encoded_scene(color=(180, 70, 35)):
    image = np.full((220, 340, 3), (8, 8, 8), np.uint8)
    cv2.rectangle(image, (20, 20), (300, 190), color, -1)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def clip_result(color, confidence=.62, second=.18, reliable=True):
    return ColorRegressorResult(
        valor=color if reliable else "DESCONOCIDO",
        confianza=confidence,
        color_hex="#123456",
        segundo_valor="NEGRO",
        segunda_confianza=second,
        margen=confidence - second,
        confiable=reliable,
    )


@pytest.mark.parametrize("color", ["AZUL", "BLANCO", "NEGRO", "GRIS"])
def test_weak_opencv_uses_clip_on_real_vehicle_crop(monkeypatch, color):
    clip = Clip(clip_result(color))
    analyzer = HybridVehicleColorAnalyzer(Detector(), clip)
    monkeypatch.setattr(analyzer.opencv, "analyze", lambda *_: [
        {"valor": "NEGRO", "cobertura": .59, "confianza": .59}
    ])

    result = analyzer.analyze(encoded_scene(), [130, 140, 190, 165])

    assert result.color_sugerido == color
    assert result.metodo_color == ("HIBRIDO" if color == "NEGRO" else "REGRESOR")
    assert clip.crops[0].shape[:2] == (170, 280)


def test_dark_background_is_not_sent_to_clip_without_associated_vehicle():
    clip = Clip(clip_result("NEGRO"))
    analyzer = HybridVehicleColorAnalyzer(Detector([]), clip)

    result = analyzer.analyze(encoded_scene((5, 5, 5)), [130, 140, 190, 165])

    assert result.color_sugerido == "DESCONOCIDO"
    assert result.metodo_color == "DESCONOCIDO"
    assert clip.crops == []


def test_low_confidence_vehicle_box_is_rejected():
    clip = Clip(clip_result("AZUL"))
    analyzer = HybridVehicleColorAnalyzer(
        Detector([Detection(confidence=.20)]), clip
    )

    result = analyzer.analyze(encoded_scene(), [130, 140, 190, 165])

    assert result.color_sugerido == "DESCONOCIDO"
    assert result.metodo_color == "DESCONOCIDO"
    assert clip.crops == []


def test_clip_small_top1_top2_margin_returns_unknown(monkeypatch):
    clip = Clip(clip_result("AZUL", confidence=.31, second=.30, reliable=False))
    analyzer = HybridVehicleColorAnalyzer(Detector(), clip)
    monkeypatch.setattr(analyzer.opencv, "analyze", lambda *_: [
        {"valor": "DESCONOCIDO", "cobertura": .2, "confianza": .3}
    ])

    result = analyzer.analyze(encoded_scene(), [130, 140, 190, 165])

    assert result.color_sugerido == "DESCONOCIDO"
    assert result.metodo_color == "DESCONOCIDO"


def test_confident_opencv_does_not_execute_clip(monkeypatch):
    clip = Clip(clip_result("ROJO"))
    analyzer = HybridVehicleColorAnalyzer(Detector(), clip)
    monkeypatch.setattr(analyzer.opencv, "analyze", lambda *_: [
        {"valor": "BLANCO", "cobertura": .9, "confianza": .82}
    ])

    result = analyzer.analyze(encoded_scene(), [130, 140, 190, 165])

    assert result.color_sugerido == "BLANCO"
    assert result.metodo_color == "OPENCV"
    assert clip.crops == []
