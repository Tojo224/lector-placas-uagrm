from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class VehicleColorSuggestion:
    color: str | None
    confidence: float


def _vehicle_body_roi(image: np.ndarray, plate_bbox: list[float] | None) -> np.ndarray:
    height, width = image.shape[:2]
    if plate_bbox and len(plate_bbox) == 4:
        x1, y1, x2, y2 = (int(value) for value in plate_bbox)
        plate_w = max(1, x2 - x1)
        plate_h = max(1, y2 - y1)
        left = max(0, x1 - 2 * plate_w)
        right = min(width, x2 + 2 * plate_w)
        top = max(0, y1 - 4 * plate_h)
        bottom = max(top + 1, min(height, y1 - plate_h // 3))
        roi = image[top:bottom, left:right]
        if roi.size and roi.shape[0] >= 12 and roi.shape[1] >= 12:
            return roi

    # Fallback conservador para capturas donde el vehículo está centrado.
    return image[int(height * 0.2):int(height * 0.72), int(width * 0.18):int(width * 0.82)]


def detect_vehicle_color(image_bytes: bytes, plate_bbox: list[float] | None) -> VehicleColorSuggestion:
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return VehicleColorSuggestion(None, 0.0)

    roi = _vehicle_body_roi(image, plate_bbox)
    if roi.size == 0:
        return VehicleColorSuggestion(None, 0.0)

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hsv = cv2.GaussianBlur(hsv, (5, 5), 0)
    h, s, v = cv2.split(hsv)
    usable = v > 10
    if int(usable.sum()) < 200:
        return VehicleColorSuggestion(None, 0.0)

    masks = {
        "Negro": usable & (v < 65),
        "Blanco": usable & (s < 45) & (v > 190),
        "Gris": usable & (s < 55) & (v >= 65) & (v <= 190),
        "Rojo": usable & (s >= 70) & ((h <= 10) | (h >= 170)),
        "Naranja": usable & (s >= 70) & (h > 10) & (h <= 22),
        "Amarillo": usable & (s >= 65) & (h > 22) & (h <= 38),
        "Verde": usable & (s >= 55) & (h > 38) & (h <= 85),
        "Azul": usable & (s >= 55) & (h > 85) & (h <= 135),
        "Morado": usable & (s >= 50) & (h > 135) & (h < 170),
    }
    counts = {name: int(mask.sum()) for name, mask in masks.items()}
    color, count = max(counts.items(), key=lambda item: item[1])
    classified = sum(counts.values())
    if classified == 0 or count < 150:
        return VehicleColorSuggestion(None, 0.0)
    confidence = min(0.95, count / classified)
    if confidence < 0.35:
        return VehicleColorSuggestion(None, round(confidence, 3))
    return VehicleColorSuggestion(color, round(confidence, 3))
