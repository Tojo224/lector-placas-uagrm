from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from app.ai.ocr_types import OCRPipelineConfig
from app.ai.validators import (
    is_blocklisted,
    normalize_plate_text,
    validate_bolivian_plate,
)

logger = logging.getLogger(__name__)

PIPELINE_MODE = "FAST_ALPR_FAST_PLATE_OCR"
PRIMARY_PIPELINE_MODE = PIPELINE_MODE
MIN_CANDIDATE_LENGTH = 4
MAX_CANDIDATE_LENGTH = 10
TARGET_PLATE_LENGTH = 7


@dataclass(frozen=True)
class OCRCandidate:
    raw_text: str
    normalized_text: str
    confidence: float
    xyxy: np.ndarray
    valid_format: bool
    score: float


def default_pipeline_config() -> OCRPipelineConfig:
    """Load central settings only for callers that do not inject OCR config."""
    from app.config.settings import settings

    return OCRPipelineConfig(
        confidence_threshold=settings.OCR_CONFIDENCE_THRESHOLD,
        roi_x=settings.OCR_ROI_X,
        roi_y=settings.OCR_ROI_Y,
        roi_width=settings.OCR_ROI_WIDTH,
        roi_height=settings.OCR_ROI_HEIGHT,
    )


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


def _configured_roi(config: OCRPipelineConfig) -> tuple[int, int, int, int] | None:
    values = (config.roi_x, config.roi_y, config.roi_width, config.roi_height)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("La ROI requiere X, Y, WIDTH y HEIGHT.")
    x, y, width, height = (int(value) for value in values)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("La ROI contiene coordenadas o dimensiones invalidas.")
    return x, y, width, height


def _extract_analysis_region(
    image: np.ndarray, config: OCRPipelineConfig
) -> tuple[np.ndarray, tuple[int, int]]:
    roi = _configured_roi(config)
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
    score = (0.55 if valid else 0.0) + 0.30 * float(np.clip(confidence, 0.0, 1.0)) + 0.08 * length_score + 0.03 * aspect_score + 0.04 * size_score
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
    return float(value or 0.0)


def _encode_image(image: np.ndarray) -> str | None:
    encoded, buffer = cv2.imencode(".jpg", image)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}" if encoded else None


def _analyze_with_fast_alpr(
    image: np.ndarray,
    analysis_region: np.ndarray,
    offset: tuple[int, int],
    plate_engine: Any,
    realtime: bool,
    config: OCRPipelineConfig,
) -> dict:
    try:
        predictions = plate_engine.predict(analysis_region)
    except Exception:
        logger.exception("FastALPR/FastPlateOCR fallo durante la inferencia")
        return _error("Error durante la inferencia FastPlateOCR.", 500, "ocr_inference_error")

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
    confirmed = selected.valid_format and selected.confidence >= config.confidence_threshold
    combined_confidence = float(np.clip(0.70 * selected.confidence + 0.30 * detector_confidence, 0.0, 1.0))
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
    if config.use_supervision_annotations:
        import supervision as sv

        detections = sv.Detections(
            xyxy=np.asarray([selected.xyxy], dtype=np.float32),
            confidence=np.asarray([combined_confidence], dtype=np.float32),
            data={"class_name": np.asarray([selected.normalized_text])},
        )
        crop = sv.crop_image(image=image, xyxy=selected.xyxy)
        annotated = sv.BoxAnnotator(
            thickness=2, color_lookup=sv.ColorLookup.INDEX
        ).annotate(scene=image.copy(), detections=detections)
        annotated = sv.LabelAnnotator(
            text_scale=0.5, color_lookup=sv.ColorLookup.INDEX
        ).annotate(
            scene=annotated,
            detections=detections,
            labels=[f"{selected.normalized_text} ({combined_confidence:.0%})"],
        )
    else:
        x1, y1, x2, y2 = (int(value) for value in selected.xyxy)
        crop = image[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
        annotated = image.copy()
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (160, 64, 160), 2)
        cv2.putText(
            annotated, f"{selected.normalized_text} ({combined_confidence:.0%})",
            (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (160, 64, 160), 1, cv2.LINE_AA,
        )
    result["annotated_image"] = _encode_image(annotated)
    result["plate_crop"] = _encode_image(crop) if crop.size else None
    return result


def analyze_plate(
    image_bytes: bytes,
    realtime: bool = False,
    plate_engine=None,
    config: OCRPipelineConfig | None = None,
) -> dict:
    if not image_bytes:
        return _error("La imagen esta vacia.", 400, "empty_image")
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return _error("No se pudo decodificar la imagen enviada.", 400, "invalid_image")
    if plate_engine is None:
        return _error("Motor FastPlateOCR no inicializado.", 503, "ocr_unavailable")
    config = config or default_pipeline_config()
    try:
        analysis_region, offset = _extract_analysis_region(image, config)
    except ValueError as exc:
        return _error(str(exc), 422, "invalid_roi")
    return _analyze_with_fast_alpr(
        image, analysis_region, offset, plate_engine, realtime, config
    )
