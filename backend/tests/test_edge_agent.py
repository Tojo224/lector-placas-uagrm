from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from edge_agent.app import create_edge_app
from edge_agent.config import EdgeSettings
from fastapi.testclient import TestClient


def fixture_image_bytes() -> bytes:
    image = np.full((180, 320, 3), 180, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def prediction(text: str = "1234ABC") -> SimpleNamespace:
    return SimpleNamespace(
        detection=SimpleNamespace(
            confidence=0.90,
            bounding_box=SimpleNamespace(x1=20, y1=70, x2=230, y2=150),
        ),
        ocr=SimpleNamespace(text=text, confidence=0.92),
    )


def fake_engine() -> MagicMock:
    engine = MagicMock()
    engine.predict.return_value = [prediction()]
    return engine


class FakeVehicleDetector:
    def predict(self, _image):
        return [SimpleNamespace(
            label="car",
            confidence=0.95,
            bounding_box=SimpleNamespace(x1=20, y1=20, x2=300, y2=170),
        )]


def test_edge_imports_without_database_or_cloudinary():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    code = (
        "import sys; import edge_agent.main; "
        "forbidden=('sqlalchemy','psycopg','alembic','cloudinary'); "
        "loaded=[name for name in sys.modules if name.split('.')[0] in forbidden]; "
        "assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_edge_rejects_non_loopback_bind(monkeypatch):
    monkeypatch.setenv("EDGE_HOST", "0.0.0.0")
    with pytest.raises(ValueError, match="127.0.0.1"):
        EdgeSettings.from_env()


def test_edge_starts_without_database_url_and_persists_analysis(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path), engine_factory=lambda _settings: fake_engine()
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/edge/analyze",
            files={"file": ("fixture.jpg", fixture_image_bytes(), "image/jpeg")},
        )
        health = client.get("/api/v1/edge/health")
        status = client.get("/api/v1/edge/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["estado"] == "DETECTADO"
    assert payload["placa_normalizada"] == "1234ABC"
    assert payload["es_registrado"] is False
    assert payload["vehiculo_id"] is None
    assert health.json()["ocr_ready"] is True
    assert health.json()["database_ready"] is True
    assert health.json()["active_ocr_engine"] == "fast_alpr"
    assert status.json()["analysis_count"] == 1
    assert status.json()["network_mode"] == "offline"
    assert (tmp_path / "data" / "edge-agent.sqlite3").exists()


def test_edge_health_is_degraded_when_ocr_cannot_start(tmp_path):
    def fail(_settings):
        raise RuntimeError("model unavailable")

    app = create_edge_app(EdgeSettings(data_dir=tmp_path), engine_factory=fail)
    with TestClient(app) as client:
        health = client.get("/api/v1/edge/health")
        analyze = client.post(
            "/api/v1/edge/analyze",
            files={"file": ("fixture.jpg", fixture_image_bytes(), "image/jpeg")},
        )

    assert health.status_code == 200
    assert health.json()["status"] == "degraded"
    assert health.json()["ocr_ready"] is False
    assert analyze.status_code == 503


def test_edge_can_restart_and_initializes_engine_once_per_start(tmp_path):
    factory = MagicMock(side_effect=lambda _settings: fake_engine())
    app = create_edge_app(EdgeSettings(data_dir=tmp_path), engine_factory=factory)

    with TestClient(app) as first_client:
        assert first_client.get("/api/v1/edge/health").json()["ocr_ready"]
        assert first_client.get("/api/v1/edge/version").status_code == 200
        response = first_client.post(
            "/api/v1/edge/analyze",
            files={"file": ("fixture.jpg", fixture_image_bytes(), "image/jpeg")},
        )
        assert response.status_code == 200
    with TestClient(app) as restarted_client:
        assert restarted_client.get("/api/v1/edge/health").json()["ocr_ready"]
        assert restarted_client.get("/api/v1/edge/status").json()["analysis_count"] == 1

    assert factory.call_count == 2


def test_edge_uses_shared_local_color_model_and_response_contract(tmp_path):
    image = np.full((190, 320, 3), (180, 85, 35), np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    plate_engine = fake_engine()
    plate_engine.predict.return_value = [SimpleNamespace(
        detection=SimpleNamespace(
            confidence=0.92,
            bounding_box=SimpleNamespace(x1=130, y1=130, x2=190, y2=160),
        ),
        ocr=SimpleNamespace(text="1234ABC", confidence=0.94),
    )]
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path),
        engine_factory=lambda _settings: plate_engine,
        color_engine_factory=lambda _settings: (FakeVehicleDetector(), None),
    )

    with TestClient(app) as client:
        health = client.get("/api/v1/edge/health").json()
        response = client.post(
            "/api/v1/edge/analyze",
            files={"file": ("blue-car.jpg", encoded.tobytes(), "image/jpeg")},
            data={"realtime": "false", "confirm": "true"},
        )

    assert health["color_ready"] is True
    assert response.status_code == 200
    payload = response.json()
    assert payload["color_sugerido"] == "AZUL"
    assert payload["color_hex"] == "#2355B4"
    assert payload["metodo_color"] == "OPENCV"
    assert isinstance(payload["confianza_color"], float)
