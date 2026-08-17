from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Sequence
from uuid import UUID
import unicodedata

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VehicleBrandModelResult:
    marca_sugerida: str | None
    modelo_sugerido: str | None
    marca_sugerida_id: UUID | None
    confianza: float
    metodo: str


class BrandModelClassifier:
    """Clasificador ONNX MobileNetV3 para marcas y modelos vehiculares."""

    DEFAULT_MEAN: ClassVar[list[float]] = [0.485, 0.456, 0.406]
    DEFAULT_STD: ClassVar[list[float]] = [0.229, 0.224, 0.225]

    def __init__(
        self,
        model_path: str | Path,
        labels_path: str | Path,
        providers: list[str] | None = None,
    ) -> None:
        import onnxruntime as ort

        self.model_path = Path(model_path)
        self.labels_path = Path(labels_path)
        self.providers = providers or ["CPUExecutionProvider"]

        if not self.model_path.exists():
            raise FileNotFoundError(f"No se encontró el modelo ONNX en {self.model_path}")
        if not self.labels_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de etiquetas en {self.labels_path}")

        with open(self.labels_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        self.labels: list[str] = metadata.get("labels", [])
        self.image_size: int = metadata.get("image_size", 224)
        self.confidence_threshold: float = float(metadata.get("confidence_threshold", 0.70))
        self.minimum_margin: float = float(metadata.get("minimum_margin", 0.10))

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=opts,
            providers=self.providers,
        )
        self.input_name = self.session.get_inputs()[0].name

    def preprocess(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Convierte recorte BGR a tensor NCHW normalizado RGB."""
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.image_size, self.image_size), interpolation=cv2.INTER_LINEAR)
        normalized = (resized.astype(np.float32) / 255.0 - self.DEFAULT_MEAN) / self.DEFAULT_STD
        # Transponer de HWC a CHW y añadir dimensión Batch -> NCHW
        tensor = np.transpose(normalized, (2, 0, 1))[np.newaxis, ...].astype(np.float32)
        return tensor

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        exp_vals = np.exp(logits - np.max(logits))
        return exp_vals / np.sum(exp_vals)

    def predict_crop(self, crop_bgr: np.ndarray) -> tuple[str | None, str | None, float]:
        """Ejecuta inferencia sobre el recorte del vehículo.
        
        Devuelve (marca, modelo, confianza). Si no supera umbrales, devuelve (None, None, confianza).
        """
        if crop_bgr is None or crop_bgr.size == 0 or min(crop_bgr.shape[:2]) < 32:
            return None, None, 0.0

        tensor = self.preprocess(crop_bgr)
        outputs = self.session.run(None, {self.input_name: tensor})
        logits = outputs[0][0]  # Shape (12,)
        probs = self._softmax(logits)

        sorted_indices = np.argsort(probs)[::-1]
        top1_idx = int(sorted_indices[0])
        top1_prob = float(probs[top1_idx])
        top2_prob = float(probs[sorted_indices[1]]) if len(sorted_indices) > 1 else 0.0

        margin = top1_prob - top2_prob
        if top1_prob < self.confidence_threshold or margin < self.minimum_margin:
            logger.debug(
                "Inferencia de marca/modelo con baja confianza: top1=%.2f (umbral=%.2f), margin=%.2f",
                top1_prob, self.confidence_threshold, margin
            )
            return None, None, round(top1_prob, 4)

        raw_label = self.labels[top1_idx]
        # Las etiquetas tienen el formato MARCA__MODELO (e.g. TOYOTA__COROLLA)
        if "__" in raw_label:
            marca_part, modelo_part = raw_label.split("__", 1)
        else:
            marca_part, modelo_part = raw_label, "DESCONOCIDO"

        marca = marca_part.replace("_", " ").title()
        modelo = modelo_part.replace("_", " ").title()
        return marca, modelo, round(top1_prob, 4)

    @classmethod
    def resolve_with_catalog(
        cls,
        crop_bgr: np.ndarray | None,
        classifier: BrandModelClassifier | None,
        brand_catalog: Sequence[Any],
    ) -> VehicleBrandModelResult:
        """Clasifica recorte y asocia la marca con el ID del catálogo si coincide."""
        if classifier is None or crop_bgr is None or crop_bgr.size == 0:
            return VehicleBrandModelResult(
                marca_sugerida=None,
                modelo_sugerido=None,
                marca_sugerida_id=None,
                confianza=0.0,
                metodo="DESCONOCIDO",
            )

        marca, modelo, conf = classifier.predict_crop(crop_bgr)
        if marca is None:
            return VehicleBrandModelResult(
                marca_sugerida=None,
                modelo_sugerido=None,
                marca_sugerida_id=None,
                confianza=conf,
                metodo="DESCONOCIDO",
            )

        norm_marca = cls._normalize_text(marca)
        marca_id = None
        for item in brand_catalog:
            item_name = getattr(item, "nombre", "")
            if cls._normalize_text(item_name) == norm_marca:
                marca_id = item.id
                break

        return VehicleBrandModelResult(
            marca_sugerida=marca,
            modelo_sugerido=modelo,
            marca_sugerida_id=marca_id,
            confianza=conf,
            metodo="ONNX_MOBILENETV3",
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value or "")
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).upper().strip()
