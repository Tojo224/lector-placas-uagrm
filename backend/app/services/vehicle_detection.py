from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any, ClassVar

import cv2
import numpy as np

@dataclass(frozen=True)
class VehicleAssociation:
    label: str
    detector_confidence: float
    bbox: tuple[int, int, int, int]
    association_quality: float
    visual_quality: float


class VehicleAssociationService:
    """Ejecuta RF-DETR una vez y asocia una placa con un vehiculo."""

    VEHICLE_LABELS: ClassVar[set[str]] = {"car", "motorcycle", "bus", "truck"}
    MIN_ASSOCIATION = 0.58
    AMBIGUITY_MARGIN = 0.08

    def __init__(self, detector: Any, confidence_threshold: float = 0.35) -> None:
        self.detector = detector
        self.confidence_threshold = confidence_threshold

    def detect_bytes(self, image_bytes: bytes, plate_bbox) -> VehicleAssociation | None:
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        return self.detect(image, plate_bbox) if image is not None else None

    def detect(self, image: np.ndarray, plate_bbox) -> VehicleAssociation | None:
        if self.detector is None or image is None or not plate_bbox or len(plate_bbox) != 4:
            return None
        detections = self.detector.predict(image)  # unica inferencia RF-DETR
        candidates = self._score_candidates(image, plate_bbox, detections)
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best = candidates[0]
        if best_score < self.MIN_ASSOCIATION:
            return None
        if len(candidates) > 1:
            second_score, _second = candidates[1]
            if second_score >= self.MIN_ASSOCIATION and best_score - second_score < self.AMBIGUITY_MARGIN:
                return None
        return best

    def _score_candidates(self, image, plate_bbox, detections):
        height, width = image.shape[:2]
        plate = self._clip_box(plate_bbox, width, height)
        if plate is None:
            return []
        plate_area = self._area(plate)
        plate_diag = hypot(plate[2] - plate[0], plate[3] - plate[1])
        results = []
        for detection in detections or []:
            label = str(getattr(detection, "label", "")).lower()
            confidence = float(getattr(detection, "confidence", 0.0))
            if label not in self.VEHICLE_LABELS or confidence < self.confidence_threshold:
                continue
            raw = getattr(detection, "bounding_box", None)
            if raw is None:
                continue
            box = self._clip_box((raw.x1, raw.y1, raw.x2, raw.y2), width, height)
            if box is None or min(box[2] - box[0], box[3] - box[1]) < 48:
                continue
            expanded = self._expand(box, width, height, 0.04)
            coverage = self._intersection_area(plate, expanded) / max(1.0, plate_area)
            gap = self._box_gap(plate, expanded) / max(1.0, plate_diag)
            proximity = float(np.clip(1.0 - gap / 1.5, 0.0, 1.0))
            plate_ratio = plate_area / max(1.0, self._area(box))
            relative_quality = self._relative_size_quality(plate_ratio)
            association = float(np.clip(
                0.40 * coverage + 0.20 * proximity + 0.25 * confidence + 0.15 * relative_quality,
                0.0, 1.0,
            ))
            if coverage < 0.45 and gap > 0.35:
                continue
            crop = image[box[1]:box[3], box[0]:box[2]]
            visual = self.visual_quality(crop, image.shape)
            result = VehicleAssociation(label, confidence, box, association, visual)
            results.append((association, result))
        return results

    @staticmethod
    def visual_quality(crop: np.ndarray, image_shape) -> float:
        if crop is None or crop.size == 0 or min(crop.shape[:2]) < 48:
            return 0.0
        image_area = max(1.0, float(image_shape[0] * image_shape[1]))
        size_quality = float(np.clip((crop.shape[0] * crop.shape[1] / image_area) / 0.18, 0.0, 1.0))
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blur_quality = float(np.clip(cv2.Laplacian(gray, cv2.CV_32F).var() / 180.0, 0.0, 1.0))
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        values = hsv[:, :, 2]
        bad_light = float(np.mean((values < 18) | (values > 247)))
        exposure_quality = float(np.clip(1.0 - bad_light / 0.45, 0.0, 1.0))
        return float(np.clip(0.45 * size_quality + 0.30 * blur_quality + 0.25 * exposure_quality, 0.0, 1.0))

    @staticmethod
    def _relative_size_quality(ratio: float) -> float:
        if ratio < 0.0002 or ratio > 0.18:
            return 0.0
        ideal = 0.018
        return float(np.clip(1.0 - abs(np.log(max(ratio, 1e-6) / ideal)) / 4.0, 0.0, 1.0))

    @staticmethod
    def _clip_box(box, width, height):
        x1, y1, x2, y2 = map(float, box)
        clipped = (max(0, int(x1)), max(0, int(y1)), min(width, int(x2)), min(height, int(y2)))
        return clipped if clipped[2] > clipped[0] and clipped[3] > clipped[1] else None

    @staticmethod
    def _expand(box, width, height, fraction):
        dx, dy = (box[2] - box[0]) * fraction, (box[3] - box[1]) * fraction
        return (max(0, int(box[0] - dx)), max(0, int(box[1] - dy)),
                min(width, int(box[2] + dx)), min(height, int(box[3] + dy)))

    @staticmethod
    def _area(box):
        return max(0, box[2] - box[0]) * max(0, box[3] - box[1])

    @classmethod
    def _intersection_area(cls, first, second):
        return cls._area((max(first[0], second[0]), max(first[1], second[1]),
                          min(first[2], second[2]), min(first[3], second[3])))

    @staticmethod
    def _box_gap(first, second):
        dx = max(second[0] - first[2], first[0] - second[2], 0)
        dy = max(second[1] - first[3], first[1] - second[3], 0)
        return hypot(dx, dy)
