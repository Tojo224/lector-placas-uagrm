from __future__ import annotations

from pathlib import Path

import pytest

from edge_agent.app import create_edge_app
from edge_agent.config import EdgeSettings
from fastapi.testclient import TestClient

from tests.test_edge_agent import fake_engine, fixture_image_bytes

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_edge_serves_react_build_and_spa_routes_offline(tmp_path):
    frontend = tmp_path / "frontend-dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "index.html").write_text("<html>edge scanner</html>", encoding="utf-8")
    (assets / "app.js").write_text("window.edge=true", encoding="utf-8")
    (assets / "app.css").write_text("body{}", encoding="utf-8")
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path, frontend_dir=frontend),
        engine_factory=lambda _settings: fake_engine(),
    )
    with TestClient(app) as client:
        root = client.get("/")
        nested = client.get("/subir-placa")
        asset = client.get("/assets/app.js")
        stylesheet = client.get("/assets/app.css")
        missing_asset = client.get("/assets/missing.js")
        missing_api = client.get("/api/does-not-exist")
    assert root.status_code == 200 and "edge scanner" in root.text
    assert nested.status_code == 200 and "edge scanner" in nested.text
    assert asset.headers["cache-control"].endswith("immutable")
    assert asset.headers["content-type"] == "application/javascript"
    assert stylesheet.headers["content-type"] == "text/css; charset=utf-8"
    assert missing_asset.status_code == 404
    assert "edge scanner" not in missing_asset.text
    assert missing_api.status_code == 404


@pytest.mark.parametrize(
    ("filename", "expected_content_type"),
    [
        ("app.js", "application/javascript"),
        ("app.css", "text/css; charset=utf-8"),
        ("chunk.mjs", "application/javascript"),
        ("manifest.json", "application/json"),
        ("logo.svg", "image/svg+xml"),
        ("runtime.wasm", "application/wasm"),
    ],
)
def test_edge_static_mime_types_are_independent_from_windows(
    tmp_path, monkeypatch, filename, expected_content_type
):
    frontend = tmp_path / "frontend-dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "index.html").write_text("<html>edge scanner</html>", encoding="utf-8")
    (assets / filename).write_bytes(b"asset")
    monkeypatch.setattr("mimetypes.guess_type", lambda *_args, **_kwargs: ("text/plain", None))
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path, frontend_dir=frontend),
        engine_factory=lambda _settings: fake_engine(),
    )
    with TestClient(app) as client:
        response = client.get(f"/assets/{filename}")
    assert response.status_code == 200
    assert response.headers["content-type"] == expected_content_type


def test_missing_assets_never_use_spa_fallback_when_assets_dir_is_absent(tmp_path):
    frontend = tmp_path / "frontend-dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>edge scanner</html>", encoding="utf-8")
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path, frontend_dir=frontend),
        engine_factory=lambda _settings: fake_engine(),
    )
    with TestClient(app) as client:
        response = client.get("/assets/missing.js")
    assert response.status_code == 404
    assert "edge scanner" not in response.text


def test_edge_cors_supports_local_dev_and_private_network_preflight(tmp_path):
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path), engine_factory=lambda _settings: fake_engine()
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/edge/status",
            headers={"Origin": "https://localhost:5173",
                     "Access-Control-Request-Method": "GET",
                     "Access-Control-Request-Private-Network": "true"},
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://localhost:5173"
    assert response.headers["access-control-allow-private-network"] == "true"


def test_realtime_polling_is_ocr_only_and_does_not_create_domain_events(tmp_path):
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path), engine_factory=lambda _settings: fake_engine()
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/edge/analyze?realtime=true&confirm=false",
            files={"file": ("frame.jpg", fixture_image_bytes(), "image/jpeg")},
        )
        status = client.get("/api/v1/edge/status").json()
    assert response.status_code == 200
    assert response.json()["decision"] == "OCR_ONLY"
    assert status["analysis_count"] == 0


def test_scanner_source_uses_only_edge_client_for_critical_flow():
    scanner = (REPO_ROOT / "frontend/src/pages/device/UploadPlate.jsx").read_text(
        encoding="utf-8"
    )
    edge_client = (REPO_ROOT / "frontend/src/api/edge.js").read_text(encoding="utf-8")
    assert 'from "../../api/edge"' in scanner
    assert 'from "../../api/plates"' not in scanner
    assert "analyzeWithEdge(formData, true, controller.signal, false)" in scanner
    assert "confirmedForm" in scanner
    assert "/api/v1/plates/analyze" not in scanner + edge_client
    assert "127.0.0.1:8765/api/v1/edge" in edge_client


def test_central_administration_clients_remain_separate():
    users = (REPO_ROOT / "frontend/src/pages/admin/Users.jsx").read_text(encoding="utf-8")
    devices = (REPO_ROOT / "frontend/src/api/devices.js").read_text(encoding="utf-8")
    central = (REPO_ROOT / "frontend/src/api/axios.js").read_text(encoding="utf-8")
    assert "centralApiClient" in central
    assert 'from "../../api/auth"' in users
    assert 'from "./axios"' in devices


def test_edge_configuration_only_requests_central_url():
    source = (REPO_ROOT / "frontend/src/pages/device/EdgeProvisioning.jsx").read_text(
        encoding="utf-8"
    )
    assert "central_url" in source
    assert "device_id" not in source
    assert "device_key" not in source
    assert "ID del dispositivo" not in source
    assert "Clave Edge" not in source


def test_edge_scanner_login_allows_only_admin_and_operator():
    routes = (REPO_ROOT / "frontend/src/routes/AppRoutes.jsx").read_text(
        encoding="utf-8"
    )
    context = (REPO_ROOT / "frontend/src/context/AuthContext.jsx").read_text(
        encoding="utf-8"
    )
    assert 'const EDGE_ROLES = new Set(["ADMINISTRADOR", "OPERADOR"])' in context
    assert '<Route path="/login" element={<Login />} />' in routes
    assert "EdgeScannerRoute" in routes
    assert '["ADMINISTRADOR", "OPERADOR"].includes(user.rol)' in routes


def test_central_device_role_remains_in_central_routes_and_model():
    routes = (REPO_ROOT / "frontend/src/routes/AppRoutes.jsx").read_text(
        encoding="utf-8"
    )
    models = (REPO_ROOT / "backend/app/db/models.py").read_text(encoding="utf-8")
    assert '"DISPOSITIVO"' in routes
    assert "DISPOSITIVO = \"DISPOSITIVO\"" in models
