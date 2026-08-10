from __future__ import annotations

from pathlib import Path
import json
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from edge_agent.app import create_edge_app
from edge_agent.config import EdgeSettings
from edge_agent.credentials import DeviceCredentialProvider
from edge_agent.credentials import WindowsDpapiCredentialProvider
from edge_agent.product_config import ProductConfigStore
from edge_agent.engine import bundled_model_paths
from edge_agent.runtime import configure_offline_model_runtime


class StubCredentialProvider(DeviceCredentialProvider):
    value = "provided-by-native-store"

    def get_device_key(self) -> str | None:
        return self.value

    def store_device_key(self, value: str) -> None:
        self.value = value


def test_settings_use_credential_provider(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EDGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("EDGE_DEVICE_KEY", raising=False)

    settings = EdgeSettings.from_env(StubCredentialProvider())

    assert settings.device_key == "provided-by-native-store"


def test_frontend_defaults_to_runtime_resource(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EDGE_FRONTEND_DIR", raising=False)
    settings = EdgeSettings(data_dir=tmp_path)

    assert settings.resolved_frontend_dir().parts[-2:] == ("frontend", "dist")


def test_model_runtime_is_forced_offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")

    configure_offline_model_runtime()

    assert __import__("os").environ["HF_HUB_OFFLINE"] == "1"
    assert __import__("os").environ["TRANSFORMERS_OFFLINE"] == "1"


def test_bundled_model_lookup_is_all_or_nothing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("edge_agent.engine.resource_path", lambda *_: tmp_path)
    assert bundled_model_paths() is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_round_trip_is_not_plaintext(tmp_path: Path):
    path = tmp_path / "device-key.dpapi"
    provider = WindowsDpapiCredentialProvider(path)
    secret = "edge-secret-never-plaintext"
    provider.store_device_key(secret)

    assert provider.get_device_key() == secret
    assert secret.encode() not in path.read_bytes()


def test_product_config_contains_only_non_sensitive_values(tmp_path: Path):
    store = ProductConfigStore(tmp_path)
    store.save("https://central.example", "device-id")

    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["central_url"] == "https://central.example"
    assert payload["device_id"] == "device-id"
    assert "key" not in " ".join(payload).lower()


def test_local_provision_validates_snapshot_and_never_writes_plain_key(
    monkeypatch, tmp_path: Path
):
    credential = StubCredentialProvider()
    snapshot = {
        "version": "snapshot-1", "generated_at": "2026-08-09T00:00:00+00:00",
        "vehicles": [], "devices": [],
    }

    class FakeAsyncClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, path):
            assert path == "/api/v1/edge-sync/snapshot"
            return httpx.Response(200, json=snapshot, request=httpx.Request("GET", "https://central.example" + path))
        async def aclose(self): return None

        def __init__(self, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer edge-setup-key"

    monkeypatch.setattr("edge_agent.app.httpx.AsyncClient", FakeAsyncClient)
    app = create_edge_app(
        EdgeSettings(data_dir=tmp_path),
        engine_factory=lambda _settings: object(),
        credential_provider=credential,
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/edge/provision", json={
            "central_url": "https://central.example",
            "device_id": "00000000-0000-4000-8000-000000000001",
            "device_key": "edge-setup-key",
        })

    assert response.status_code == 200
    assert credential.get_device_key() == "edge-setup-key"
    assert "edge-setup-key" not in (tmp_path / "config" / "agent.json").read_text()
