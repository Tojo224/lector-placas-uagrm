from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import supervision as sv
from app.ai.validators import (
    is_blocklisted,
    normalize_plate_text,
    validate_bolivian_plate,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)

PIPELINE_MODE = "FAST_ALPR_FAST_PLATE_OCR"
PRIMARY_PIPELINE_MODE = PIPELINE_MODE
MIN_CANDIDATE_LENGTH = 4
MAX_CANDIDATE_LENGTH = 10
TARGET_PLATE_LENGTH = 7

# Scoring weights for plate candidate ranking (empirical, from field validation)
_SCORE_VALID_FORMAT_WEIGHT = 0.55
_SCORE_CONFIDENCE_WEIGHT = 0.30
_SCORE_LENGTH_WEIGHT = 0.08
_SCORE_ASPECT_WEIGHT = 0.03
_SCORE_SIZE_WEIGHT = 0.02
_SCORE_POSITION_WEIGHT = 0.02

# Combined confidence: weight between OCR confidence and detector confidence
_COMBINED_OCR_WEIGHT = 0.70
_COMBINED_DETECTOR_WEIGHT = 0.30


box_annotator = sv.BoxAnnotator(thickness=2, color_lookup=sv.ColorLookup.INDEX)
label_annotator = sv.LabelAnnotator(text_scale=0.5, color_lookup=sv.ColorLookup.INDEX)


@dataclass(frozen=True)
class OCRCandidate:
    raw_text: str
    normalized_text: str
    confidence: float
    xyxy: np.ndarray
    valid_format: bool
    score: float


def _error(message: str, http_status: int = 422, error_code: str = "pipeline_error") -> dict:
    return {
        "status": "ERROR",
        "message": message,
        "http_status": http_status,
        "error_code": error_code,
        "requires_manual_review": False,
        "detection_backend": PIPELINE_MODE,
    }


def get_pipeline_status() -> dict[str, object]:
    return {
        "supervision_available": True,
        "camera_capture_supported": True,
        "pipeline_mode": PIPELINE_MODE,
    }


def _configured_roi() -> tuple[int, int, int, int] | None:
    values = (settings.OCR_ROI_X, settings.OCR_ROI_Y, settings.OCR_ROI_WIDTH, settings.OCR_ROI_HEIGHT)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("La ROI requiere X, Y, WIDTH y HEIGHT.")
    x, y, width, height = (int(value) for value in values)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("La ROI contiene coordenadas o dimensiones invalidas.")
    return x, y, width, height


def _extract_analysis_region(image: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    roi = _configured_roi()
    if roi is None:
        return image, (0, 0)
    x, y, width, height = roi
    image_height, image_width = image.shape[:2]
    if x + width > image_width or y + height > image_height:
        raise ValueError(
            f"La ROI ({x}, {y}, {width}, {height}) excede la imagen de {image_width}x{image_height}."
        )
    return image[y : y + height, x : x + width], (x, y)


def _candidate_score(normalized: str, confidence: float, xyxy: np.ndarray, image_shape: tuple[int, ...]) -> tuple[bool, float]:
    valid = validate_bolivian_plate(normalized)
    length_score = max(0.0, 1.0 - abs(len(normalized) - TARGET_PLATE_LENGTH) / 4.0)
    width = max(0.0, float(xyxy[2] - xyxy[0]))
    height = max(0.0, float(xyxy[3] - xyxy[1]))
    aspect_score = 1.0 if height and 1.5 <= width / height <= 6.5 else 0.25
    image_area = max(1.0, float(image_shape[0] * image_shape[1]))
    size_score = min(1.0, ((width * height) / image_area) / 0.01) if width and height else 0.0
    # Position is not independently measurable for the current detector, so its
    # weight remains part of the size term's established baseline.
    score = (
        _SCORE_VALID_FORMAT_WEIGHT * (1.0 if valid else 0.0)
        + _SCORE_CONFIDENCE_WEIGHT * float(np.clip(confidence, 0.0, 1.0))
        + _SCORE_LENGTH_WEIGHT * length_score
        + _SCORE_ASPECT_WEIGHT * aspect_score
        + (_SCORE_SIZE_WEIGHT + _SCORE_POSITION_WEIGHT) * size_score
    )
    return valid, float(np.clip(score, 0.0, 1.0))


def _make_candidate(raw_text: str, confidence: float, xyxy: np.ndarray, image_shape: tuple[int, ...]) -> OCRCandidate | None:
    normalized = normalize_plate_text(raw_text)
    if not MIN_CANDIDATE_LENGTH <= len(normalized) <= MAX_CANDIDATE_LENGTH:
        return None
    if is_blocklisted(normalized) or is_blocklisted(raw_text.strip()):
        return None
    if float(xyxy[2] - xyxy[0]) < 4 or float(xyxy[3] - xyxy[1]) < 4:
        return None
    valid, score = _candidate_score(normalized, confidence, xyxy, image_shape)
    return OCRCandidate(raw_text.strip(), normalized, float(np.clip(confidence, 0.0, 1.0)), xyxy.astype(np.float32), valid, score)


def _confidence_value(value: Any) -> float:
    if isinstance(value, (list, tuple, np.ndarray)):
        values = [float(item) for item in value]
        return float(np.mean(values)) if values else 0.0
    return float(value) if value is not None else 0.0


def _encode_image(image: np.ndarray) -> str | None:
    encoded, buffer = cv2.imencode(".jpg", image)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}" if encoded else None


def _analyze_with_fast_alpr(image: np.ndarray, analysis_region: np.ndarray, offset: tuple[int, int], plate_engine: Any, realtime: bool) -> dict:
    _t0 = time.monotonic()
    try:
        predictions = plate_engine.predict(analysis_region)
    except Exception:
        elapsed = time.monotonic() - _t0
        logger.error("FastALPR/FastPlateOCR inference failed after %.3fs", elapsed, exc_info=True)
        return {
            "status": "DEGRADED",
            "message": "El motor OCR primario falló durante la inferencia.",
            "fallback_attempted": False,
            "ocr_unavailable": True,
            "detection_backend": PIPELINE_MODE,
            "requires_manual_review": True,
            "raw_bboxes": [],
        }

    raw_bboxes: list[list[float]] = []
    candidates: list[tuple[OCRCandidate, float]] = []
    for prediction in predictions or []:
        detection = getattr(prediction, "detection", None)
        box = getattr(detection, "bounding_box", None) if detection is not None else None
        if box is None:
            continue
        xyxy = np.asarray([box.x1 + offset[0], box.y1 + offset[1], box.x2 + offset[0], box.y2 + offset[1]], dtype=np.float32)
        raw_bboxes.append(xyxy.tolist())
        ocr = getattr(prediction, "ocr", None)
        if ocr is None:
            continue
        candidate = _make_candidate(str(getattr(ocr, "text", "")), _confidence_value(getattr(ocr, "confidence", 0.0)), xyxy, image.shape)
        if candidate is not None:
            candidates.append((candidate, float(getattr(detection, "confidence", 0.0))))

    if not candidates:
        return {"status": "LOW_CONFIDENCE", "message": "FastPlateOCR no encontro una placa legible en la imagen.", "detection_backend": PIPELINE_MODE, "requires_manual_review": True, "raw_bboxes": raw_bboxes}

    candidates.sort(key=lambda item: (item[0].valid_format, item[0].score, item[0].confidence, item[1]), reverse=True)
    selected, detector_confidence = candidates[0]
    confirmed = selected.valid_format and selected.confidence >= settings.OCR_CONFIDENCE_THRESHOLD
    combined_confidence = float(np.clip(_COMBINED_OCR_WEIGHT * selected.confidence + _COMBINED_DETECTOR_WEIGHT * detector_confidence, 0.0, 1.0))
    result = {
        "status": "DETECTED" if confirmed else "LOW_CONFIDENCE",
        "message": None if confirmed else "La lectura FastPlateOCR requiere revision manual.",
        "detected_plate": selected.raw_text,
        "normalized_plate": selected.normalized_text if confirmed else None,
        "is_valid_bolivian_format": selected.valid_format,
        "detection_backend": PIPELINE_MODE,
        "detection_confidence": detector_confidence,
        "ocr_confidence": selected.confidence,
        "combined_confidence": combined_confidence,
        "requires_manual_review": not confirmed,
        "plate_bbox": [float(value) for value in selected.xyxy],
        "raw_bboxes": raw_bboxes,
    }
    if realtime:
        return result
    selected_detection = sv.Detections(xyxy=np.asarray([selected.xyxy], dtype=np.float32), confidence=np.asarray([combined_confidence], dtype=np.float32), data={"class_name": np.asarray([selected.normalized_text])})
    crop = sv.crop_image(image=image, xyxy=selected.xyxy)
    annotated = box_annotator.annotate(scene=image.copy(), detections=selected_detection)
    annotated = label_annotator.annotate(scene=annotated, detections=selected_detection, labels=[f"{selected.normalized_text} ({combined_confidence:.0%})"])
    result["annotated_image"] = _encode_image(annotated)
    result["plate_crop"] = _encode_image(crop) if crop.size else None
    return result


def analyze_plate(image_bytes: bytes, realtime: bool = False, plate_engine=None) -> dict:
    if not image_bytes:
        return _error("La imagen esta vacia.", 400, "empty_image")
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return _error("No se pudo decodificar la imagen enviada.", 400, "invalid_image")
    if plate_engine is None:
        return _error("Motor FastPlateOCR no inicializado.", 503, "ocr_unavailable")
    try:
        analysis_region, offset = _extract_analysis_region(image)
    except ValueError as exc:
        return _error(str(exc), 422, "invalid_roi")
    _t0 = time.monotonic()
    try:
        return _analyze_with_fast_alpr(image, analysis_region, offset, plate_engine, realtime)
    except Exception:
        elapsed = time.monotonic() - _t0
        logger.error("FastALPR/FastPlateOCR pipeline crashed after %.3fs", elapsed, exc_info=True)
        return {
            "status": "DEGRADED",
            "message": "Error inesperado en el pipeline de análisis.",
            "fallback_attempted": False,
            "ocr_unavailable": True,
            "detection_backend": PIPELINE_MODE,
            "requires_manual_review": True,
            "raw_bboxes": [],
        }
