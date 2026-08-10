from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from app.config.settings import BACKEND_DIR, settings


@dataclass(frozen=True)
class ColorRegressorResult:
    valor: str
    confianza: float
    color_hex: str
    segundo_valor: str
    segunda_confianza: float
    margen: float
    confiable: bool


class ColorRegressorClassifier:
    """Clasificador de color mediante regresion MobileNetV3-Small ONNX."""

    CATALOG_RGB = {
        "BLANCO": (235, 235, 235),
        "NEGRO": (28, 28, 28),
        "GRIS": (105, 105, 105),
        "PLATEADO": (178, 178, 178),
        "ROJO": (190, 40, 40),
        "AZUL": (35, 85, 180),
        "VERDE": (65, 145, 65),
        "AMARILLO": (220, 205, 35),
        "MARRON": (115, 75, 45),
    }

    MODEL_DIR = BACKEND_DIR / ".runtime" / "models"

    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir or self.MODEL_DIR
        model_path = self.model_dir / settings.COLOR_REGRESSOR_MODEL_FILE
        self.session = ort.InferenceSession(
            str(model_path),
            providers=[settings.FAST_ALPR_EXECUTION_PROVIDER],
        )

    def classify(self, vehicle_crop: np.ndarray) -> ColorRegressorResult:
        pixel_values = self._preprocess(vehicle_crop)
        # Ejecutar inferencia ONNX del regresor de color
        outputs = self.session.run(
            ["output"],
            {"input": pixel_values},
        )[0][0]  # Retorna el vector [R, G, B] normalizado en [0, 1]

        # Desnormalizar a enteros RGB [0, 255]
        r = int(np.clip(outputs[0] * 255.0, 0, 255))
        g = int(np.clip(outputs[1] * 255.0, 0, 255))
        b = int(np.clip(outputs[2] * 255.0, 0, 255))
        
        color_hex = f"#{r:02X}{g:02X}{b:02X}"

        # Clasificar mediante distancia euclidiana en el espacio RGB contra el catálogo base
        predicted_rgb = (r, g, b)
        distances = []
        for name, rgb in self.CATALOG_RGB.items():
            dist = np.linalg.norm(np.array(predicted_rgb) - np.array(rgb))
            distances.append((name, dist))
        
        distances.sort(key=lambda item: item[1])
        first_name, first_dist = distances[0]
        second_name, second_dist = distances[1]

        # Normalizar distancias a escala de confianza [0, 1]
        first_score = float(np.clip(1.0 - (first_dist / 200.0), 0.0, 1.0))
        second_score = float(np.clip(1.0 - (second_dist / 200.0), 0.0, 1.0))
        margin = first_score - second_score

        # Determinar si la clasificación del color es confiable
        reliable = first_score >= 0.35

        return ColorRegressorResult(
            valor=first_name if reliable else "DESCONOCIDO",
            confianza=first_score,
            color_hex=color_hex,
            segundo_valor=second_name,
            segunda_confianza=second_score,
            margen=margin,
            confiable=reliable,
        )

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        if image is None or image.size == 0:
            raise ValueError("El recorte vehicular esta vacio")
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA)
        
        crop = resized.astype(np.float32) / 255.0
        mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
        crop = (crop - mean) / std
        
        return np.transpose(crop, (2, 0, 1))[None, ...].astype(np.float32)
