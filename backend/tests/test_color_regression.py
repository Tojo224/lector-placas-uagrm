import os
from pathlib import Path
import cv2
import numpy as np
import pytest
from app.services.color_regressor import ColorRegressorClassifier


def test_color_regressor_loads_and_runs():
    # Asegurar que el modelo ONNX dummy existe antes de ejecutar la prueba
    model_path = Path(__file__).parent.parent / ".runtime" / "models" / "color_regression.onnx"
    assert model_path.exists(), f"El modelo ONNX no se encuentra en {model_path}"

    classifier = ColorRegressorClassifier()
    assert classifier.session is not None

    # Generar una imagen sintética verde (BGR: 0, 255, 0)
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[:, :] = (0, 255, 0)

    result = classifier.classify(image)
    
    assert result.valor in classifier.CATALOG_RGB or result.valor == "DESCONOCIDO"
    assert isinstance(result.confianza, float)
    assert result.color_hex.startswith("#")
    assert len(result.color_hex) == 7
    assert isinstance(result.confiable, bool)


def test_color_regressor_preprocess_shape():
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    preprocessed = ColorRegressorClassifier._preprocess(image)
    
    # Debe ser de la forma (1, 3, 224, 224) para coincidir con la entrada esperada de MobileNetV3
    assert preprocessed.shape == (1, 3, 224, 224)
    assert preprocessed.dtype == np.float32


def test_color_regressor_empty_crop_raises_error():
    with pytest.raises(ValueError):
        ColorRegressorClassifier._preprocess(None)
    with pytest.raises(ValueError):
        ColorRegressorClassifier._preprocess(np.empty((0, 0, 3), dtype=np.uint8))
