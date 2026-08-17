import json
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.vehicle_brand_model import BrandModelClassifier, VehicleBrandModelResult


class DummyBrand:
    def __init__(self, id, nombre):
        self.id = id
        self.nombre = nombre


def test_brand_model_classifier_load_and_predict(tmp_path):
    # Probar con los archivos reales si existen
    model_path = Path("models/brand-model-v4-bolivia12.onnx")
    labels_path = Path("models/brand-model-v4-bolivia12.labels.json")

    if not model_path.exists() or not labels_path.exists():
        pytest.skip("Modelo ONNX de marcas y modelos no disponible en models/")

    classifier = BrandModelClassifier(model_path=model_path, labels_path=labels_path)
    assert len(classifier.labels) == 12
    assert classifier.image_size == 224

    # Generar un crop sintético BGR
    dummy_crop = np.full((224, 224, 3), 128, dtype=np.uint8)
    marca, modelo, conf = classifier.predict_crop(dummy_crop)
    assert isinstance(conf, float)
    assert 0.0 <= conf <= 1.0


def test_brand_model_resolve_with_catalog():
    mock_classifier = MagicMock(spec=BrandModelClassifier)
    mock_classifier.predict_crop.return_value = ("Toyota", "Corolla", 0.92)

    toyota_id = uuid4()
    nissan_id = uuid4()
    catalog = [
        DummyBrand(toyota_id, "Toyota"),
        DummyBrand(nissan_id, "Nissan"),
    ]

    dummy_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    result = BrandModelClassifier.resolve_with_catalog(
        crop_bgr=dummy_crop,
        classifier=mock_classifier,
        brand_catalog=catalog,
    )

    assert result.marca_sugerida == "Toyota"
    assert result.modelo_sugerido == "Corolla"
    assert result.marca_sugerida_id == toyota_id
    assert result.confianza == 0.92
    assert result.metodo == "ONNX_MOBILENETV3"


def test_brand_model_resolve_unknown():
    mock_classifier = MagicMock(spec=BrandModelClassifier)
    mock_classifier.predict_crop.return_value = (None, None, 0.45)

    catalog = [DummyBrand(uuid4(), "Toyota")]
    dummy_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    result = BrandModelClassifier.resolve_with_catalog(
        crop_bgr=dummy_crop,
        classifier=mock_classifier,
        brand_catalog=catalog,
    )

    assert result.marca_sugerida is None
    assert result.modelo_sugerido is None
    assert result.marca_sugerida_id is None
    assert result.confianza == 0.45
    assert result.metodo == "DESCONOCIDO"
