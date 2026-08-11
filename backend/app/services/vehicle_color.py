from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

import cv2
import numpy as np
import supervision as sv

from app.config.settings import settings
from app.services.color_regressor import ColorRegressorClassifier
from app.services.vehicle_detection import VehicleAssociation, VehicleAssociationService


@dataclass(frozen=True)
class ColorSuggestion:
    valor: str
    cobertura: float
    confianza: float

    def to_dict(self) -> dict[str, str | float]:
        return asdict(self)


@dataclass(frozen=True)
class VehicleColorResult:
    color_sugerido: str
    confianza_color: float
    metodo_color: str
    color_hex: str | None = None
    vehicle_bbox: tuple[int, int, int, int] | None = None


class HybridVehicleColorAnalyzer:
    """Coordina deteccion vehicular, OpenCV y el respaldo local del Regresor."""

    DEFAULT_HEX = {
        "BLANCO": "#EBEBEB",
        "NEGRO": "#1C1C1C",
        "GRIS": "#696969",
        "PLATEADO": "#B2B2B2",
        "ROJO": "#BE2828",
        "AZUL": "#2355B4",
        "VERDE": "#419141",
        "AMARILLO": "#DCCD23",
        "MARRON": "#734B2D",
    }

    def __init__(self, vehicle_detector: Any, clip_classifier: ColorRegressorClassifier) -> None:
        self.vehicle_detector = vehicle_detector
        self.clip_classifier = clip_classifier
        self.opencv = VehicleColorAnalyzer()

    def analyze(
        self,
        image_bytes: bytes,
        plate_bbox,
        association: VehicleAssociation | None = None,
    ) -> VehicleColorResult:
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return VehicleColorResult("DESCONOCIDO", 0.0, "DESCONOCIDO")

        association = association or VehicleAssociationService(self.vehicle_detector).detect(image, plate_bbox)
        if association is None:
            # CLIP nunca recibe la escena completa ni una region inferida desde la placa.
            return VehicleColorResult("DESCONOCIDO", 0.0, "DESCONOCIDO")

        vehicle_bbox = association.bbox
        suggestions = self.opencv.analyze(image_bytes, plate_bbox, vehicle_bbox)
        visible = self.opencv.visible_value(suggestions)
        confidence = self.opencv.average_confidence(suggestions)
        ambiguous = self._is_ambiguous(suggestions)

        needs_fallback = (
            visible == "DESCONOCIDO"
            or confidence < settings.CLIP_COLOR_FALLBACK_THRESHOLD
            or ambiguous
        )
        if not needs_fallback:
            primary_color = visible.split(" / ")[0]
            color_hex = self.DEFAULT_HEX.get(primary_color)
            return VehicleColorResult(visible, round(confidence, 4), "OPENCV", color_hex, vehicle_bbox)

        # Solo ejecutamos el regresor si OpenCV es ambiguo o no es confiable
        crop = sv.crop_image(image=image, xyxy=np.asarray(vehicle_bbox, dtype=np.float32))
        reg_result = self.clip_classifier.classify(crop)
        color_hex = reg_result.color_hex if reg_result.confiable else None

        if not reg_result.confiable:
            return VehicleColorResult("DESCONOCIDO", 0.0, "DESCONOCIDO", None, vehicle_bbox)

        opencv_colors = {item["valor"] for item in suggestions if item["valor"] != "DESCONOCIDO"}
        method = "HIBRIDO" if reg_result.valor in opencv_colors else "REGRESOR"
        if method == "HIBRIDO":
            combined = 0.50 * confidence + 0.50 * reg_result.confianza
            return VehicleColorResult(reg_result.valor, round(combined, 4), method, color_hex, vehicle_bbox)
        return VehicleColorResult(reg_result.valor, round(reg_result.confianza, 4), method, color_hex, vehicle_bbox)

    @staticmethod
    def _is_ambiguous(suggestions: list[dict[str, str | float]]) -> bool:
        valid = [item for item in suggestions if item.get("valor") != "DESCONOCIDO"]
        if len(valid) < 2:
            return False
        first, second = valid[:2]
        return (
            abs(float(first.get("cobertura", 0)) - float(second.get("cobertura", 0))) < 0.12
            or abs(float(first.get("confianza", 0)) - float(second.get("confianza", 0))) < 0.08
        )


class VehicleColorAnalyzer:
    """Sugiere color de carroceria con OpenCV, sin modelos entrenados."""

    UNKNOWN = ColorSuggestion("DESCONOCIDO", 0.0, 0.0)
    MAX_DIMENSION = 640
    MIN_VALID_PIXELS = 500
    NEUTRAL_COLORS: ClassVar[set[str]] = {"BLANCO", "PLATEADO", "GRIS"}
    CHROMATIC_BGR: ClassVar[dict[str, tuple[int, int, int]]] = {
        "ROJO": (40, 40, 190),
        "AZUL": (180, 85, 35),
        "VERDE": (65, 145, 65),
        "AMARILLO": (35, 205, 220),
        "NARANJA": (25, 125, 225),
        "MARRON": (45, 75, 115),
    }

    def __init__(self) -> None:
        palette = np.asarray(list(self.CHROMATIC_BGR.values()), dtype=np.uint8).reshape(-1, 1, 3)
        self._chromatic_names = tuple(self.CHROMATIC_BGR)
        self._chromatic_lab = cv2.cvtColor(palette, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)

    def analyze(
        self,
        image_bytes: bytes,
        plate_bbox: list[float] | tuple[float, ...] | None,
        vehicle_bbox: list[float] | tuple[float, ...] | None = None,
    ) -> list[dict[str, str | float]]:
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return [self.UNKNOWN.to_dict()]
        crop_box = self._vehicle_box(image.shape, plate_bbox, vehicle_bbox)
        if crop_box is None:
            return [self.UNKNOWN.to_dict()]
        crop = sv.crop_image(image=image, xyxy=np.asarray(crop_box, dtype=np.float32))
        if crop.size == 0 or min(crop.shape[:2]) < 24:
            return [self.UNKNOWN.to_dict()]

        scale = min(1.0, self.MAX_DIMENSION / max(crop.shape[:2]))
        if scale < 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        mask, light_stability = self._body_mask(crop, crop_box, plate_bbox, scale)
        valid_count = int(np.count_nonzero(mask))
        valid_ratio = valid_count / max(1.0, float(crop.shape[0] * crop.shape[1]))
        if valid_count < self.MIN_VALID_PIXELS or valid_ratio < 0.07 or light_stability < 0.35:
            return [self.UNKNOWN.to_dict()]

        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
        valid_lab = lab[mask > 0]
        sample = self._sample_pixels(valid_lab)
        cluster_count = min(5, max(2, len(sample) // 700))
        cv2.setRNGSeed(17)
        _, _, centers = cv2.kmeans(
            sample,
            cluster_count,
            None,
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 35, 0.45),
            5,
            cv2.KMEANS_PP_CENTERS,
        )

        distances_to_centers = np.linalg.norm(valid_lab[:, None, :] - centers[None, :, :], axis=2)
        valid_labels = np.argmin(distances_to_centers, axis=1)
        label_map = np.full(mask.shape, -1, dtype=np.int16)
        label_map[mask > 0] = valid_labels

        color_masks: dict[str, np.ndarray] = {}
        color_fit: dict[str, list[tuple[float, int]]] = {}
        for index, center in enumerate(centers):
            name, palette_distance = self._classify_center(center)
            cluster_mask = np.uint8(label_map == index) * 255
            cluster_mask = self._retain_paint_regions(cluster_mask, valid_count)
            count = int(np.count_nonzero(cluster_mask))
            if count == 0:
                continue
            color_masks[name] = cv2.bitwise_or(color_masks.get(name, np.zeros_like(mask)), cluster_mask)
            color_fit.setdefault(name, []).append((palette_distance, count))

        # Variaciones de luminosidad de una misma pintura acromatica no son bicolor.
        neutral_present = [name for name in self.NEUTRAL_COLORS if name in color_masks]
        if len(neutral_present) > 1:
            merged = np.zeros_like(mask)
            for name in neutral_present:
                merged = cv2.bitwise_or(merged, color_masks.pop(name))
            neutral_name, neutral_distance = self._neutral_from_pixels(crop[merged > 0])
            if neutral_name == "DESCONOCIDO":
                return [self.UNKNOWN.to_dict()]
            color_masks[neutral_name] = merged
            color_fit[neutral_name] = [(neutral_distance, int(np.count_nonzero(merged)))]

        suggestions: list[ColorSuggestion] = []
        diagnostics: dict[str, tuple[float, float, int]] = {}
        for name, color_mask in color_masks.items():
            count = int(np.count_nonzero(color_mask))
            coverage = count / max(1, valid_count)
            coherence, sectors = self._spatial_coherence(color_mask, count)
            fit_entries = color_fit.get(name, [(80.0, count)])
            fit_distance = sum(distance * weight for distance, weight in fit_entries) / max(1, sum(weight for _, weight in fit_entries))
            palette_fit = float(np.clip(1.0 - fit_distance / 75.0, 0.0, 1.0))
            # Cobertura no es confianza: pesa poco y solo indica cuanta pintura
            # util respalda el resultado. La estabilidad de iluminacion, el ajuste
            # cromatico y la coherencia espacial dominan la puntuacion calibrada.
            confidence = float(np.clip(
                0.15 * min(coverage / 0.65, 1.0)
                + 0.25 * palette_fit
                + 0.20 * coherence
                + 0.10 * min(valid_ratio / 0.30, 1.0)
                + 0.30 * light_stability,
                0.0,
                1.0,
            ))
            diagnostics[name] = (coherence, coverage, sectors)
            suggestions.append(ColorSuggestion(name, round(coverage, 4), round(confidence, 4)))

        suggestions.sort(key=lambda item: (item.cobertura, item.confianza), reverse=True)
        if not suggestions or suggestions[0].cobertura < 0.30 or suggestions[0].confianza < 0.40:
            best = suggestions[0] if suggestions else self.UNKNOWN
            return [ColorSuggestion("DESCONOCIDO", best.cobertura, best.confianza).to_dict()]

        selected = [suggestions[0]]
        if len(suggestions) > 1:
            second = suggestions[1]
            coherence, coverage, sectors = diagnostics[second.valor]
            primary = suggestions[0]
            # El segundo color debe ser una superficie extensa, continua y presente
            # en mas de un sector; piezas negras y reflejos no cumplen estas reglas.
            # Varias piezas pintadas pueden quedar separadas por una franja bicolor;
            # por eso se permite coherencia moderada, pero se exigen cobertura y
            # presencia horizontal amplia.
            meaningful = coverage >= 0.25 and coherence >= 0.40 and sectors >= 2
            if second.valor == "NEGRO" and primary.valor in {"BLANCO", "PLATEADO", "GRIS"}:
                meaningful = meaningful and coverage >= 0.34
            if second.confianza >= 0.45 and meaningful:
                selected.append(second)
        return [item.to_dict() for item in selected]

    @staticmethod
    def visible_value(suggestions: list[dict[str, str | float]]) -> str:
        values = [str(item["valor"]) for item in suggestions if item.get("valor") != "DESCONOCIDO"]
        return " / ".join(values) if values else "DESCONOCIDO"

    @staticmethod
    def average_confidence(suggestions: list[dict[str, str | float]]) -> float:
        valid = [item for item in suggestions if item.get("valor") != "DESCONOCIDO"]
        total_coverage = sum(float(item.get("cobertura", 0.0)) for item in valid)
        if total_coverage <= 0:
            return 0.0
        return sum(
            float(item.get("confianza", 0.0)) * float(item.get("cobertura", 0.0))
            for item in valid
        ) / total_coverage

    @staticmethod
    def _vehicle_box(image_shape, plate_bbox, vehicle_bbox):
        height, width = image_shape[:2]
        if vehicle_bbox and len(vehicle_bbox) == 4:
            x1, y1, x2, y2 = map(float, vehicle_bbox)
        else:
            return None
        clipped = (max(0, int(x1)), max(0, int(y1)), min(width, int(x2)), min(height, int(y2)))
        return clipped if clipped[2] > clipped[0] and clipped[3] > clipped[1] else None

    @staticmethod
    def _body_mask(crop, crop_box, plate_bbox, scale):
        height, width = crop.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        body = np.asarray([[(int(.09*width), int(.25*height)), (int(.91*width), int(.25*height)),
                            (int(.96*width), int(.66*height)), (int(.80*width), int(.84*height)),
                            (int(.20*width), int(.84*height)), (int(.04*width), int(.66*height))]], np.int32)
        cv2.fillPoly(mask, body, 255)

        # Ventanas/cabina, parrilla central y ruedas son zonas sistematicamente no pintadas.
        window = np.asarray([[ (int(.27*width), int(.24*height)), (int(.73*width), int(.24*height)),
                               (int(.67*width), int(.47*height)), (int(.33*width), int(.47*height)) ]], np.int32)
        grille = np.asarray([[ (int(.31*width), int(.64*height)), (int(.69*width), int(.64*height)),
                               (int(.63*width), int(.84*height)), (int(.37*width), int(.84*height)) ]], np.int32)
        cv2.fillPoly(mask, window, 0)
        cv2.fillPoly(mask, grille, 0)
        cv2.ellipse(mask, (int(.16*width), int(.79*height)), (int(.14*width), int(.18*height)), 0, 0, 360, 0, -1)
        cv2.ellipse(mask, (int(.84*width), int(.79*height)), (int(.14*width), int(.18*height)), 0, 0, 360, 0, -1)

        if plate_bbox and len(plate_bbox) == 4:
            px1, py1, px2, py2 = map(float, plate_bbox)
            local = np.asarray([(px1-crop_box[0])*scale, (py1-crop_box[1])*scale,
                                (px2-crop_box[0])*scale, (py2-crop_box[1])*scale]).astype(int)
            pad_x = max(4, int((local[2]-local[0])*.35))
            pad_y = max(4, int((local[3]-local[1])*.45))
            cv2.rectangle(mask, (max(0, local[0]-pad_x), max(0, local[1]-pad_y)),
                          (min(width, local[2]+pad_x), min(height, local[3]+pad_y)), 0, -1)

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        saturation, value = hsv[:, :, 1], hsv[:, :, 2]
        candidate_count = max(1, int(np.count_nonzero(mask)))
        reflection_ratio = float(np.count_nonzero((value >= 240) & (mask > 0)) / candidate_count)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        texture = cv2.magnitude(gx, gy)
        deep_shadow = value < 24
        strong_reflection = (value > 240) | ((value > 230) & (saturation > 70))
        mechanical_texture = texture > 115
        mask[deep_shadow | strong_reflection | mechanical_texture] = 0
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        light_stability = VehicleColorAnalyzer._light_stability(
            mask, saturation, value, reflection_ratio
        )
        return mask, light_stability

    @staticmethod
    def _light_stability(mask, saturation, value, reflection_ratio=0.0):
        valid = mask > 0
        if np.count_nonzero(valid) < VehicleColorAnalyzer.MIN_VALID_PIXELS:
            return 0.0
        values = value[valid].astype(np.float32)
        saturations = saturation[valid].astype(np.float32)
        p05, p25, p75, p95 = np.percentile(values, [5, 25, 75, 95])
        spread = float(p95 - p05)
        middle_spread = float(p75 - p25)
        overexposed = reflection_ratio
        shadows = float(np.mean(values <= 28))

        sector_medians = []
        width = mask.shape[1]
        for index in range(3):
            sector = valid[:, int(index * width / 3):int((index + 1) * width / 3)]
            sector_values = value[:, int(index * width / 3):int((index + 1) * width / 3)][sector]
            if len(sector_values) >= 100:
                sector_medians.append(float(np.median(sector_values)))
        spatial_range = max(sector_medians) - min(sector_medians) if len(sector_medians) >= 2 else 100.0
        low_saturation = float(np.mean(saturations < 35))

        # Un neutro autentico puede tener baja saturacion; se rechaza cuando esa
        # falta de cromaticidad viene acompanada de iluminacion muy desigual.
        if (overexposed > 0.12 or (shadows > 0.35 and (spread > 60 or spatial_range > 50))
                or spatial_range > 95
                or (low_saturation > 0.80 and (spread > 105 or middle_spread > 60))):
            return 0.0
        penalties = (
            0.30 * min(spread / 130.0, 1.0)
            + 0.25 * min(middle_spread / 70.0, 1.0)
            + 0.20 * min(spatial_range / 80.0, 1.0)
            + 0.15 * min(overexposed / 0.12, 1.0)
            + 0.10 * min(shadows / 0.35, 1.0)
        )
        return float(np.clip(1.0 - penalties, 0.0, 1.0))

    @staticmethod
    def _sample_pixels(pixels):
        if len(pixels) <= 14000:
            return pixels
        return pixels[np.linspace(0, len(pixels)-1, 14000, dtype=np.int32)]

    @staticmethod
    def _retain_paint_regions(mask, valid_count):
        components, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        retained = np.zeros_like(mask)
        minimum = max(70, int(valid_count * 0.012))
        for index in range(1, components):
            if stats[index, cv2.CC_STAT_AREA] >= minimum:
                retained[labels == index] = 255
        return retained

    @staticmethod
    def _spatial_coherence(mask, count):
        components, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        largest = max((stats[i, cv2.CC_STAT_AREA] for i in range(1, components)), default=0)
        coherence = largest / max(1, count)
        width = mask.shape[1]
        sectors = 0
        for index in range(3):
            x1, x2 = int(index * width / 3), int((index + 1) * width / 3)
            if np.count_nonzero(mask[:, x1:x2]) >= max(25, int(count * 0.08)):
                sectors += 1
        return float(coherence), sectors

    def _classify_center(self, center):
        lab_pixel = np.uint8(np.clip(center, 0, 255)).reshape(1, 1, 3)
        bgr = cv2.cvtColor(lab_pixel, cv2.COLOR_LAB2BGR)
        _h, s, v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).reshape(3).astype(float)
        # Metales gris/plateado adquieren tintes del cielo, cesped o edificios;
        # una saturacion moderada no basta para convertirlos en marron/verde.
        if s <= 90:
            if v >= 210:
                return "BLANCO", abs(v - 235) * 0.6
            if v >= 150:
                return "PLATEADO", abs(v - 178) * 0.7
            if v >= 62:
                return "GRIS", abs(v - 105) * 0.7
            return "NEGRO", abs(v - 28) * 0.7
        distances = np.linalg.norm(self._chromatic_lab - center.astype(np.float32), axis=1)
        index = int(np.argmin(distances))
        return self._chromatic_names[index], float(distances[index])

    @staticmethod
    def _neutral_from_pixels(pixels):
        if not len(pixels):
            return "GRIS", 75.0
        hsv = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
        values = hsv[:, 2].astype(np.float32)
        saturations = hsv[:, 1].astype(np.float32)
        p10, p25, median, p75, p90 = np.percentile(values, [10, 25, 50, 75, 90])
        spread = float(p90 - p10)
        median_saturation = float(np.median(saturations))
        if spread > 105 or (median_saturation < 30 and p75 - p25 > 60):
            return "DESCONOCIDO", 75.0
        # Blanco exige que tambien los cuartiles bajos sean claros; un gris con
        # reflejos no puede convertirse en blanco por unas pocas zonas quemadas.
        if median >= 210 and p25 >= 195 and p90 >= 225 and spread <= 55:
            return "BLANCO", abs(median - 235) * 0.6 + spread * 0.15
        if median >= 145 and p25 >= 115:
            return "PLATEADO", abs(median - 175) * 0.55 + spread * 0.12
        if median >= 55:
            return "GRIS", abs(median - 105) * 0.55 + spread * 0.10
        return "NEGRO", abs(median - 28) * 0.6 + spread * 0.10
