from __future__ import annotations

import base64
import logging
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
MPLCONFIG_DIR = RUNTIME_DIR / "matplotlib"
MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

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

PIPELINE_MODE = "OCR_SUPERVISION"
OCR_ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
MIN_CANDIDATE_LENGTH = 4
MAX_CANDIDATE_LENGTH = 10
TARGET_PLATE_LENGTH = 7
MAX_REALTIME_DIM = 480  # OPT-A: 480px suficiente para leer placa, ~44% menos píxeles que 640px
MAX_STATIC_DIM = 1280   # EFI-002: Resolución límite para pipeline estático (1-2 MP)
OCR_UPSCALE_THRESHOLD = 600  # OPT-C: Solo aplicar upscale si lado más largo < este valor

box_annotator = sv.BoxAnnotator(thickness=2, color_lookup=sv.ColorLookup.INDEX)
label_annotator = sv.LabelAnnotator(
    text_scale=0.5,
    color_lookup=sv.ColorLookup.INDEX,
)


@dataclass(frozen=True)
class OCRCandidate:
    raw_text: str
    normalized_text: str
    confidence: float
    xyxy: np.ndarray
    valid_format: bool
    score: float
    source_count: int = 1


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
    values = (
        settings.OCR_ROI_X,
        settings.OCR_ROI_Y,
        settings.OCR_ROI_WIDTH,
        settings.OCR_ROI_HEIGHT,
    )
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
            f"La ROI ({x}, {y}, {width}, {height}) excede la imagen "
            f"de {image_width}x{image_height}."
        )
    return image[y : y + height, x : x + width], (x, y)


def _preprocess_image(image: np.ndarray) -> tuple[np.ndarray, float]:
    processed: np.ndarray
    if settings.OCR_USE_GRAYSCALE:
        processed = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if settings.OCR_USE_CONTRAST:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            processed = clahe.apply(processed)
    else:
        processed = image.copy()
        if settings.OCR_USE_CONTRAST:
            processed = cv2.convertScaleAbs(processed, alpha=1.15, beta=0)

    if settings.OCR_DENOISE:
        processed = cv2.GaussianBlur(processed, (3, 3), 0)

    if settings.OCR_USE_THRESHOLD:
        if processed.ndim == 3:
            processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        _, processed = cv2.threshold(
            processed,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )

    scale = 1.0
    factor = float(settings.OCR_UPSCALE_FACTOR)
    # OPT-C: Solo escalar si la imagen es pequeña; imágenes >= OCR_UPSCALE_THRESHOLD
    # ya tienen suficiente resolución — escalar cuadriplica el área sin ganancia real.
    if factor > 1.0 and max(processed.shape[:2]) < OCR_UPSCALE_THRESHOLD:
        processed = cv2.resize(
            processed,
            None,
            fx=factor,
            fy=factor,
            interpolation=cv2.INTER_CUBIC,
        )
        scale = factor
    return processed, scale


def _detections_from_paddle(paddle_results: list[Any]) -> sv.Detections:
    """Convierte resultados de PaddleOCR al formato sv.Detections.

    PaddleOCR devuelve una lista de:
        [ [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], (texto, confianza) ]

    Se extrae el bounding box xyxy a partir del polígono cuadrilátero.
    """
    if not paddle_results:
        return sv.Detections.empty()

    boxes_xyxy: list[np.ndarray] = []
    confidences: list[float] = []
    texts: list[str] = []

    for item in paddle_results:
        try:
            box_pts, text_conf = item
            text, conf = text_conf
        except (TypeError, ValueError):
            continue
        pts = np.array(box_pts, dtype=np.float32)
        x1 = float(pts[:, 0].min())
        y1 = float(pts[:, 1].min())
        x2 = float(pts[:, 0].max())
        y2 = float(pts[:, 1].max())
        boxes_xyxy.append(np.array([x1, y1, x2, y2], dtype=np.float32))
        confidences.append(float(conf))
        texts.append(str(text))

    if not boxes_xyxy:
        return sv.Detections.empty()

    return sv.Detections(
        xyxy=np.stack(boxes_xyxy),
        confidence=np.array(confidences, dtype=np.float32),
        data={"class_name": np.array(texts)},
    )

def _map_detections_to_image(
    detections: sv.Detections,
    scale: float,
    offset: tuple[int, int],
    image_shape: tuple[int, ...],
) -> sv.Detections:
    if len(detections) == 0:
        return detections
    xyxy = detections.xyxy.astype(np.float32).copy() / scale
    xyxy[:, [0, 2]] += offset[0]
    xyxy[:, [1, 3]] += offset[1]
    image_height, image_width = image_shape[:2]
    xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, image_width)
    xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, image_height)
    return sv.Detections(
        xyxy=xyxy,
        confidence=detections.confidence,
        data=detections.data,
    )


def _candidate_score(
    normalized: str,
    confidence: float,
    xyxy: np.ndarray,
    image_shape: tuple[int, ...],
) -> tuple[bool, float]:
    valid = validate_bolivian_plate(normalized)
    length_score = max(0.0, 1.0 - abs(len(normalized) - TARGET_PLATE_LENGTH) / 4.0)
    width = max(0.0, float(xyxy[2] - xyxy[0]))
    height = max(0.0, float(xyxy[3] - xyxy[1]))
    aspect_ratio = width / height if height else 0.0
    aspect_score = 1.0 if 1.5 <= aspect_ratio <= 6.5 else 0.25
    image_area = max(1.0, float(image_shape[0] * image_shape[1]))
    area_ratio = (width * height) / image_area
    size_score = min(1.0, area_ratio / 0.01) if area_ratio > 0 else 0.0
    center_x = float(xyxy[0] + xyxy[2]) / 2.0 / max(1.0, float(image_shape[1]))
    center_y = float(xyxy[1] + xyxy[3]) / 2.0 / max(1.0, float(image_shape[0]))
    position_score = 1.0 if 0.03 <= center_x <= 0.97 and 0.03 <= center_y <= 0.97 else 0.5
    score = (
        (0.55 if valid else 0.0)
        + 0.30 * float(np.clip(confidence, 0.0, 1.0))
        + 0.08 * length_score
        + 0.03 * aspect_score
        + 0.02 * size_score
        + 0.02 * position_score
    )
    return valid, float(np.clip(score, 0.0, 1.0))


def _make_candidate(
    raw_text: str,
    confidence: float,
    xyxy: np.ndarray,
    image_shape: tuple[int, ...],
    source_count: int = 1,
) -> OCRCandidate | None:
    normalized = normalize_plate_text(raw_text)
    if not MIN_CANDIDATE_LENGTH <= len(normalized) <= MAX_CANDIDATE_LENGTH:
        return None
    # Descartar palabras del entorno de la placa (BOLIVIA, POLICIA, etc.)
    if is_blocklisted(normalized) or is_blocklisted(raw_text.strip()):
        logger.debug("_make_candidate: descartado por blocklist -> %r", normalized)
        return None
    width = float(xyxy[2] - xyxy[0])
    height = float(xyxy[3] - xyxy[1])
    if width < 4 or height < 4:
        return None
    valid, score = _candidate_score(normalized, confidence, xyxy, image_shape)
    return OCRCandidate(
        raw_text=raw_text.strip(),
        normalized_text=normalized,
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        xyxy=xyxy.astype(np.float32),
        valid_format=valid,
        score=score,
        source_count=source_count,
    )


def _boxes_are_near(left: np.ndarray, right: np.ndarray) -> bool:
    if right[0] < left[0]:
        left, right = right, left
    left_height = max(1.0, float(left[3] - left[1]))
    right_height = max(1.0, float(right[3] - right[1]))
    vertical_overlap = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    overlap_ratio = vertical_overlap / min(left_height, right_height)
    horizontal_gap = float(right[0] - left[2])
    max_width = max(float(left[2] - left[0]), float(right[2] - right[0]), 1.0)
    return overlap_ratio >= 0.4 and -0.25 * max_width <= horizontal_gap <= 1.25 * max_width


def _build_candidates(
    detections: sv.Detections,
    image_shape: tuple[int, ...],
) -> list[OCRCandidate]:
    if len(detections) == 0:
        return []
    texts = detections.data.get("class_name") if detections.data else None
    if texts is None:
        return []
    confidences = (
        detections.confidence
        if detections.confidence is not None
        else np.zeros(len(detections), dtype=np.float32)
    )
    candidates: list[OCRCandidate] = []
    for index, text in enumerate(texts):
        candidate = _make_candidate(
            str(text),
            float(confidences[index]),
            detections.xyxy[index],
            image_shape,
        )
        if candidate is not None:
            candidates.append(candidate)

    for first_index in range(len(detections)):
        for second_index in range(first_index + 1, len(detections)):
            first_box = detections.xyxy[first_index]
            second_box = detections.xyxy[second_index]
            if not _boxes_are_near(first_box, second_box):
                continue
            ordered = sorted(
                ((first_box, str(texts[first_index]), float(confidences[first_index])),
                 (second_box, str(texts[second_index]), float(confidences[second_index]))),
                key=lambda item: float(item[0][0]),
            )
            raw_text = " ".join(item[1].strip() for item in ordered)
            weights = [max(1, len(normalize_plate_text(item[1]))) for item in ordered]
            confidence = float(np.average([item[2] for item in ordered], weights=weights))
            union = np.asarray(
                [
                    min(first_box[0], second_box[0]),
                    min(first_box[1], second_box[1]),
                    max(first_box[2], second_box[2]),
                    max(first_box[3], second_box[3]),
                ],
                dtype=np.float32,
            )
            candidate = _make_candidate(raw_text, confidence, union, image_shape, source_count=2)
            if candidate is not None:
                candidates.append(candidate)

    unique: dict[tuple[str, int, int, int, int], OCRCandidate] = {}
    for candidate in candidates:
        key = (candidate.normalized_text, *(int(value) for value in candidate.xyxy))
        previous = unique.get(key)
        if previous is None or candidate.score > previous.score:
            unique[key] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (item.valid_format, item.score, item.confidence),
        reverse=True,
    )


def _encode_image(image: np.ndarray) -> str | None:
    encoded, buffer = cv2.imencode(".jpg", image)
    if not encoded:
        return None
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"


def _resize_for_realtime(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Redimensiona la imagen para que el lado más largo sea MAX_REALTIME_DIM."""
    h, w = image.shape[:2]
    if max(h, w) <= MAX_REALTIME_DIM:
        return image, 1.0
    if w > h:
        scale = MAX_REALTIME_DIM / w
    else:
        scale = MAX_REALTIME_DIM / h
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return resized, scale

def _resize_for_static(image: np.ndarray) -> tuple[np.ndarray, float]:
    """EFI-002: Limita el tamaño de la imagen subida para el pipeline estático."""
    h, w = image.shape[:2]
    if max(h, w) <= MAX_STATIC_DIM:
        return image, 1.0
    
    scale = MAX_STATIC_DIM / float(max(h, w))
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return resized, scale


def _run_ocr(
    ocr_reader,
    processed: np.ndarray,
    text_threshold: float = 0.7,
    low_text: float = 0.4,
    realtime: bool = False,
) -> list:
    """Ejecuta PaddleOCR con parámetros optimizados para números de placa."""
    # PaddleOCR v3.0 requiere imágenes con 3 canales (HxWxC). Si es escala de grises, convertimos a BGR.
    if len(processed.shape) == 2:
        processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
    raw = ocr_reader.ocr(processed)
    
    # Si es el nuevo PaddleOCR (v3.0+) devuelve una lista de diccionarios
    if raw and isinstance(raw[0], dict):
        res_dict = raw[0]
        polys = res_dict.get("rec_polys", []) or res_dict.get("dt_polys", [])
        texts = res_dict.get("rec_texts", [])
        scores = res_dict.get("rec_scores", [])
        results = []
        for poly, text, score in zip(polys, texts, scores):
            results.append([poly, (text, score)])
    else:
        results = raw[0] if raw and raw[0] else []

    # Filtrar por allowlist (A-Z, 0-9, guion) y por umbral de confianza mínimo.
    # PaddleOCR no tiene parámetro allowlist directo; se aplica aquí antes de
    # que normalize_plate_text() limpie los caracteres finales.
    filtered: list = []
    for item in results:
        try:
            box_pts, text_conf = item
            text, conf = text_conf
        except (TypeError, ValueError):
            continue
        if float(conf) < low_text:
            continue
        # Conservar texto que contenga al menos 1 carácter de la allowlist
        cleaned = "".join(c for c in str(text).upper() if c in OCR_ALLOWLIST)
        if not cleaned:
            continue
        filtered.append(item)

    return filtered


def _generate_preprocessing_variants(
    image: np.ndarray,
) -> list[tuple[str, np.ndarray, float]]:
    """
    Genera múltiples variantes de preprocesamiento de la imagen.
    Retorna lista de (nombre, imagen_procesada, escala).
    Intentar varias variantes aumenta la probabilidad de que PaddleOCR lea bien la placa.
    """
    variants: list[tuple[str, np.ndarray, float]] = []

    def _upscale(img: np.ndarray, factor: float) -> tuple[np.ndarray, float]:
        h, w = img.shape[:2]
        # OPT-C: Respetar umbral — no escalar imágenes ya grandes
        if factor > 1.0 and max(h, w) < OCR_UPSCALE_THRESHOLD:
            img = cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
            return img, factor
        return img, 1.0

    factor = float(settings.OCR_UPSCALE_FACTOR)

    # Calcular gris una sola vez — reutilizado por múltiples variantes
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # OPT-B: Ordenadas de más rápida a más lenta para maximizar el early-exit.
    # bilateral_sharp tarda ~50ms solo en preproceso, se reserva como último recurso.

    # Variante 1: escala de grises + CLAHE — la más efectiva y rápida para placas bien iluminadas
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray_clahe = clahe.apply(gray)
    v1, s1 = _upscale(gray_clahe, factor)
    variants.append(("gray_clahe", v1, s1))

    # Variante 2: threshold adaptativo — buena para placas con luz desigual (~8ms preproceso)
    v2_base = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 5
    )
    v2, s2 = _upscale(v2_base, factor)
    variants.append(("adaptive_thresh", v2, s2))

    # Variante 3: erosión leve — une trazos rotos (ej. 'D' en placa), ~6ms preproceso
    kernel_erode = np.ones((2, 2), np.uint8)
    eroded = cv2.erode(gray, kernel_erode, iterations=1)
    v3, s3 = _upscale(eroded, factor)
    variants.append(("morph_erode", v3, s3))

    # Variante 4: imagen original sin modificar (upscale si es pequeña)
    v4, s4 = _upscale(image.copy(), factor)
    variants.append(("original", v4, s4))

    # Variante 5: bilateral filter + sharpening — último recurso (~50ms preproceso)
    bilateral = cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)
    kernel_sharp = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    sharpened = cv2.filter2D(bilateral, -1, kernel_sharp)
    v5, s5 = _upscale(sharpened, factor)
    variants.append(("bilateral_sharp", v5, s5))

    return variants


def analyze_plate(image_bytes: bytes, ocr_reader=None, realtime: bool = False) -> dict:
    if not image_bytes:
        return _error("La imagen esta vacia.", http_status=400, error_code="empty_image")

    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return _error(
            "No se pudo decodificar la imagen enviada.",
            http_status=400,
            error_code="invalid_image",
        )
    if ocr_reader is None:
        return _error("Motor OCR no inicializado.", http_status=503, error_code="ocr_unavailable")

    try:
        analysis_region, offset = _extract_analysis_region(image)
    except ValueError as exc:
        return _error(str(exc), http_status=422, error_code="invalid_roi")

    # ----------------------------------------------------------------
    # PATH REALTIME: máxima velocidad — 1 variante, 1 config, sin base64
    # ----------------------------------------------------------------
    if realtime:
        rt_region, rt_scale = _resize_for_realtime(analysis_region)

        # ---- Variante principal: escala de grises + CLAHE ----
        gray = cv2.cvtColor(rt_region, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        processed_main = clahe.apply(gray)

        candidates_rt: list[OCRCandidate] = []
        raw_bboxes_rt: list[list[float]] = []

        try:
            # Umbrales equilibrados: suficiente para leer bien, estrictos para evitar ruido
            results = _run_ocr(ocr_reader, processed_main, 0.6, 0.35, realtime=True)
        except Exception as exc:
            logger.warning("OCR realtime (principal) fallo: %s", exc)
            results = []

        if results:
            det = _detections_from_paddle(results)
            det = _map_detections_to_image(det, rt_scale, offset, image.shape)
            raw_bboxes_rt.extend(det.xyxy.tolist())
            candidates_rt.extend(_build_candidates(det, image.shape))

        # ---- Variante fallback: threshold adaptativo ----
        # OPT-A: Solo lanzar si la variante principal detectó texto (results > 0)
        # pero no produjo un candidato con formato boliviano válido.
        # Si la imagen está vacía (0 resultados), no gastar otra llamada OCR.
        has_valid = any(c.valid_format and c.confidence >= settings.OCR_CONFIDENCE_THRESHOLD for c in candidates_rt)
        primary_found_text = bool(results)
        if not has_valid and primary_found_text:
            try:
                processed_fb = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 5
                )
                results_fb = _run_ocr(ocr_reader, processed_fb, 0.6, 0.35, realtime=True)
            except Exception as exc:
                logger.warning("OCR realtime (fallback) fallo: %s", exc)
                results_fb = []

            if results_fb:
                det_fb = _detections_from_paddle(results_fb)
                det_fb = _map_detections_to_image(det_fb, rt_scale, offset, image.shape)
                raw_bboxes_rt.extend(det_fb.xyxy.tolist())
                candidates_rt.extend(_build_candidates(det_fb, image.shape))

        if not candidates_rt:
            return {
                "status": "LOW_CONFIDENCE",
                "message": "Sin texto detectado en la imagen.",
                "detection_backend": PIPELINE_MODE,
                "requires_manual_review": True,
                "raw_bboxes": raw_bboxes_rt,
            }

        # Ordenar y seleccionar el mejor candidato
        candidates_rt.sort(key=lambda c: (c.valid_format, c.score, c.confidence), reverse=True)
        selected = candidates_rt[0]
        confirmed = selected.valid_format and selected.confidence >= settings.OCR_CONFIDENCE_THRESHOLD

        return {
            "status": "DETECTED" if confirmed else "LOW_CONFIDENCE",
            "message": None if confirmed else "Texto detectado, esperando confirmación.",
            # Siempre retornar detected_plate para que el frontend pueda acumular votos
            "detected_plate": selected.raw_text,
            "normalized_plate": selected.normalized_text if confirmed else None,
            "is_valid_bolivian_format": selected.valid_format,
            "detection_backend": PIPELINE_MODE,
            "detection_confidence": selected.score,
            "ocr_confidence": selected.confidence,
            "combined_confidence": selected.score,
            "requires_manual_review": not confirmed,
            # Sin annotated_image ni plate_crop para mantener velocidad
            "plate_bbox": [float(c) for c in selected.xyxy],
            "raw_bboxes": raw_bboxes_rt,
        }

    # ----------------------------------------------------------------
    # PATH ESTÁTICO: máxima precisión — multi-variante + multi-config
    # ----------------------------------------------------------------
    static_region, static_scale = _resize_for_static(analysis_region)
    variants = _generate_preprocessing_variants(static_region)

    ocr_configs = [
        (0.7, 0.4),   # Normal
        (0.4, 0.2),   # Sensible: detecta texto de baja confianza
    ]

    all_candidates: list[OCRCandidate] = []
    all_raw_bboxes: list[list[float]] = []

    for var_name, processed, scale in variants:
        for text_thr, low_thr in ocr_configs:
            try:
                results = _run_ocr(ocr_reader, processed, text_thr, low_thr, realtime=False)
            except Exception as exc:
                logger.warning("OCR fallo en variante '%s' cfg=(%.1f,%.1f): %s", var_name, text_thr, low_thr, exc)
                continue

            logger.debug(
                "Variante '%s' cfg=(%.1f,%.1f): %d detecciones %s",
                var_name,
                text_thr,
                low_thr,
                len(results or []),
                [(r[1][0], round(r[1][1], 2)) for r in (results or [])],
            )

            if not results:
                continue

            det = _detections_from_paddle(results)
            # Combinamos la escala estática con el offset original
            det = _map_detections_to_image(det, static_scale, offset, image.shape)
            all_raw_bboxes.extend(det.xyxy.tolist())
            candidates = _build_candidates(det, image.shape)
            all_candidates.extend(candidates)

            if any(
                c.valid_format and c.confidence >= settings.OCR_CONFIDENCE_THRESHOLD
                for c in candidates
            ):
                logger.debug("Candidato válido encontrado en variante '%s', deteniendo búsqueda.", var_name)
                break

        else:
            continue
        break

    if not all_candidates:
        return {
            "status": "LOW_CONFIDENCE",
            "message": "El motor OCR no encontro texto legible en la imagen.",
            "detection_backend": PIPELINE_MODE,
            "requires_manual_review": True,
            "raw_bboxes": all_raw_bboxes,
        }

    all_candidates.sort(key=lambda c: (c.valid_format, c.score, c.confidence), reverse=True)
    seen: dict[str, OCRCandidate] = {}
    for c in all_candidates:
        if c.normalized_text not in seen or c.score > seen[c.normalized_text].score:
            seen[c.normalized_text] = c
    unique_candidates = sorted(seen.values(), key=lambda c: (c.valid_format, c.score), reverse=True)

    selected = unique_candidates[0]
    logger.debug(
        "Candidato seleccionado: '%s' | valido=%s | ocr_conf=%.2f | score=%.2f",
        selected.normalized_text,
        selected.valid_format,
        selected.confidence,
        selected.score,
    )

    selected_detection = sv.Detections(
        xyxy=np.asarray([selected.xyxy], dtype=np.float32),
        confidence=np.asarray([selected.confidence], dtype=np.float32),
        data={"class_name": np.asarray([selected.normalized_text])},
    )
    crop = sv.crop_image(image=image, xyxy=selected.xyxy)
    if crop.size == 0:
        return _error(
            "El candidato OCR no produjo un recorte valido.",
            http_status=422,
            error_code="empty_crop",
        )

    confirmed = selected.valid_format and (selected.confidence >= settings.OCR_CONFIDENCE_THRESHOLD)
    status = "DETECTED" if confirmed else "LOW_CONFIDENCE"
    message = None
    if not selected.valid_format:
        message = "El mejor texto OCR no coincide con un formato boliviano valido."
    elif not confirmed:
        message = "La lectura requiere revision manual por baja confianza OCR."

    label = f"{selected.normalized_text} ({selected.confidence:.0%})"
    annotated = box_annotator.annotate(scene=image.copy(), detections=selected_detection)
    annotated = label_annotator.annotate(
        scene=annotated, detections=selected_detection, labels=[label]
    )

    return {
        "status": status,
        "message": message,
        "detected_plate": selected.raw_text,
        "normalized_plate": selected.normalized_text if confirmed else None,
        "is_valid_bolivian_format": selected.valid_format,
        "detection_backend": PIPELINE_MODE,
        "detection_confidence": selected.score,
        "ocr_confidence": selected.confidence,
        "combined_confidence": selected.score,
        "requires_manual_review": not confirmed,
        "annotated_image": _encode_image(annotated),
        "plate_crop": _encode_image(crop),
        "plate_bbox": [float(c) for c in selected.xyxy],
        "raw_bboxes": all_raw_bboxes,
    }


def classify_vehicle_attributes(
    image: np.ndarray,
    classifier: Any,
    candidate_brands: list[str],
    candidate_types: list[str],
) -> dict[str, str | None]:
    """Clasifica marca, tipo y color de un vehículo en base a catálogos dinámicos usando CLIP.

    Para optimizar la precisión de CLIP, la clasificación interna se realiza usando
    etiquetas y prompts en inglés, traduciendo de ida y vuelta con los catálogos en español.
    """
    if classifier is None:
        return {"brand": None, "type": None, "color": None}

    # Convertir imagen numpy BGR (OpenCV) a RGB para PIL / CLIP
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # 1. Clasificación de Color (estático)
    colors_mapping = {
        "white": "Blanco",
        "black": "Negro",
        "dark grey": "Gris",
        "silver": "Plateado",
        "red": "Rojo",
        "blue": "Azul",
        "green": "Verde",
        "yellow": "Amarillo",
    }
    try:
        color_res = classifier(
            image_rgb,
            candidate_labels=list(colors_mapping.keys()),
            hypothesis_template="a photo of a {} vehicle",
        )
        best_color_en = color_res[0]["label"]
        color_val = colors_mapping.get(best_color_en)
    except Exception as exc:
        logger.warning("Fallo al clasificar color con CLIP: %s", exc)
        color_val = None

    # 2. Clasificación de Marca (dinámica del catálogo)
    # CLIP es más preciso si agregamos el contexto "car/vehicle" a marcas comunes.
    brand_val = None
    if candidate_brands:
        try:
            # Diccionario de traducción básica de marcas comunes si es necesario
            # Si no hay mapeo, se usa directamente el nombre del catálogo.
            brand_labels = [b.lower() for b in candidate_brands]
            brand_res = classifier(
                image_rgb,
                candidate_labels=brand_labels,
                hypothesis_template="a photo of a {} car",
            )
            best_brand = brand_res[0]["label"]
            # Encontrar el elemento original en la lista respetando mayúsculas/minúsculas
            for orig in candidate_brands:
                if orig.lower() == best_brand:
                    brand_val = orig
                    break
        except Exception as exc:
            logger.warning("Fallo al clasificar marca con CLIP: %s", exc)

    # 3. Clasificación de Tipo (dinámico del catálogo)
    type_val = None
    if candidate_types:
        # Traducción básica de tipos al inglés para alimentar a CLIP
        type_translation = {
            "automovil": "sedan car",
            "automóvil": "sedan car",
            "motocicleta": "motorcycle",
            "camioneta": "pickup truck",
            "vagoneta": "suv",
            "vagoneta/suv": "suv",
            "camión": "truck",
            "micro": "bus",
            "minibus": "minivan",
        }
        try:
            # Crear lista de etiquetas en inglés y mapeo inverso
            english_labels = []
            rev_mapping = {}
            for t in candidate_types:
                clean_t = t.lower().strip()
                eng = type_translation.get(clean_t, clean_t)
                english_labels.append(eng)
                rev_mapping[eng] = t

            type_res = classifier(
                image_rgb,
                candidate_labels=english_labels,
                hypothesis_template="a photo of a {} vehicle",
            )
            best_type_eng = type_res[0]["label"]
            type_val = rev_mapping.get(best_type_eng)
        except Exception as exc:
            logger.warning("Fallo al clasificar tipo con CLIP: %s", exc)

    return {"brand": brand_val, "type": type_val, "color": color_val}

