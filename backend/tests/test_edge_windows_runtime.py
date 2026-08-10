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


def test_provisioned_installation_identity_survives_settings_reload(
    monkeypatch, tmp_path: Path
):
    installation_id = "00000000-0000-4000-8000-000000000333"
    ProductConfigStore(tmp_path).save(
        "https://central.example",
        installation_id=installation_id,
        installation_provisioned=True,
    )
    credential = StubCredentialProvider()
    credential.store_device_key("installation-secret")
    monkeypatch.setenv("EDGE_DATA_DIR", str(tmp_path))

    restarted = EdgeSettings.from_env(credential)

    assert restarted.installation_id == installation_id
    assert restarted.installation_key == "installation-secret"
    assert restarted.sync_configured() is True
    assert "installation-secret" not in ProductConfigStore(tmp_path).path.read_text()


def test_local_configuration_preserves_existing_technical_credentials(
    monkeypatch, tmp_path: Path
):
    credential = StubCredentialProvider()
    credential.store_device_key("edge-setup-key")
    ProductConfigStore(tmp_path).save(
        "https://old-central.example", "00000000-0000-4000-8000-000000000001"
    )
    app = create_edge_app(
        EdgeSettings(
            data_dir=tmp_path,
            device_id="00000000-0000-4000-8000-000000000001",
            device_key="edge-setup-key",
        ),
        engine_factory=lambda _settings: object(),
        credential_provider=credential,
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/edge/provision", json={
            "central_url": "https://central.example",
        })

    assert response.status_code == 200
    assert response.json()["technical_credentials_preserved"] is True
    assert credential.get_device_key() == "edge-setup-key"
    payload = (tmp_path / "config" / "agent.json").read_text()
    assert "edge-setup-key" not in payload
    assert "00000000-0000-4000-8000-000000000001" in payload
