from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from edge_agent.app import create_edge_app
from edge_agent.config import EdgeSettings
from edge_agent.db import EdgeDatabase
from edge_agent.product_config import ProductConfigStore
from tests.test_edge_agent import fake_engine


class CentralAuthClient:
    response_status = 200
    role = "OPERADOR"
    auth_offline = False

    def __init__(self, **_kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return None

    async def post(self, path, json, **_kwargs):
        request = httpx.Request("POST", "https://central.example" + path)
        if path == "/api/v1/edge-sync/installations/provision":
            return httpx.Response(
                200,
                json={
                    "installation_id": json["installation_id"],
                    "credential": "installation-secret",
                    "issued_at": "2026-08-10T00:00:00+00:00",
                },
                request=request,
            )
        assert path == "/api/auth/login"
        assert set(json) == {"carnet", "contrasena"}
        if self.auth_offline:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(
            self.response_status,
            json={
                "token": "central-human-token-must-not-be-stored",
                "user": {
                    "id": "00000000-0000-4000-8000-000000000101",
                    "carnet": json["carnet"],
                    "rol": self.role,
                    "esta_activo": True,
                },
            },
            request=request,
        )

    async def get(self, path):
        request = httpx.Request("GET", "https://central.example" + path)
        return httpx.Response(
            200,
            json={
                "version": "v1",
                "generated_at": "2026-08-10T00:00:00+00:00",
                "vehicles": [],
                "devices": [],
            },
            request=request,
        )

    async def aclose(self): return None


class CredentialStore:
    def __init__(self): self.value = None
    def get_device_key(self): return self.value
    def store_device_key(self, value): self.value = value


class OfflineClient:
    def __init__(self, **_kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return None

    async def post(self, path, json):
        request = httpx.Request("POST", "https://central.example" + path)
        raise httpx.ConnectError("offline", request=request)

    async def aclose(self): return None


def edge_app(tmp_path, credential=None):
    ProductConfigStore(tmp_path).save("https://central.example")
    return create_edge_app(
        EdgeSettings(data_dir=tmp_path, central_url="https://central.example"),
        engine_factory=lambda _settings: fake_engine(),
        credential_provider=credential or CredentialStore(),
    )


def test_first_online_login_creates_independent_local_verifier_then_works_offline(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr("edge_agent.local_auth.httpx.AsyncClient", CentralAuthClient)
    monkeypatch.setattr("edge_agent.app.httpx.AsyncClient", CentralAuthClient)
    monkeypatch.setattr("edge_agent.sync.httpx.AsyncClient", CentralAuthClient)
    credential = CredentialStore()
    app = edge_app(tmp_path, credential)
    with TestClient(app) as client:
        online = client.post("/api/v1/edge/auth/login", json={
            "carnet": "staff-1", "contrasena": "ClaveSegura1",
        })
        token = online.json()["token"]
        session = client.get(
            "/api/v1/edge/auth/session", headers={"Authorization": f"Bearer {token}"}
        )
        logout = client.post(
            "/api/v1/edge/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )
        status_after_logout = client.get("/api/v1/edge/status")
        CentralAuthClient.auth_offline = True
        offline = client.post("/api/v1/edge/auth/login", json={
            "carnet": "staff-1", "contrasena": "ClaveSegura1",
        })
        CentralAuthClient.auth_offline = False

    assert online.status_code == 200 and online.json()["mode"] == "ONLINE"
    assert session.status_code == 200
    assert logout.status_code == 200
    assert status_after_logout.json()["sync"]["configured"] is True
    assert offline.status_code == 200 and offline.json()["mode"] == "OFFLINE"
    assert credential.value == "installation-secret"
    database = EdgeDatabase(tmp_path / "data" / "edge-agent.sqlite3")
    with database.connection() as connection:
        row = connection.execute("SELECT * FROM local_auth_users").fetchone()
    stored = " ".join(str(value) for value in row)
    assert row["role"] == "OPERADOR"
    assert row["local_verifier"].startswith("edge_pbkdf2_sha256$")
    assert "ClaveSegura1" not in stored
    assert "central-human-token" not in stored
    product_config = ProductConfigStore(tmp_path).path.read_text(encoding="utf-8")
    assert "installation-secret" not in product_config
    assert b"installation-secret" not in database.path.read_bytes()
    assert "installation-secret" not in caplog.text


def test_unknown_user_offline_must_first_login_with_internet(monkeypatch, tmp_path):
    monkeypatch.setattr("edge_agent.local_auth.httpx.AsyncClient", OfflineClient)
    app = edge_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/edge/auth/login", json={
            "carnet": "new-staff", "contrasena": "ClaveSegura1",
        })
    assert response.status_code == 401
    assert "una vez con conexión" in response.json()["detail"]


@pytest.mark.parametrize("role", ["USUARIO", "DISPOSITIVO"])
def test_online_login_never_enables_disallowed_roles(monkeypatch, tmp_path, role):
    CentralAuthClient.role = role
    monkeypatch.setattr("edge_agent.local_auth.httpx.AsyncClient", CentralAuthClient)
    app = edge_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/edge/auth/login", json={
            "carnet": "blocked", "contrasena": "ClaveSegura1",
        })
    CentralAuthClient.role = "OPERADOR"
    assert response.status_code == 403
    database = EdgeDatabase(tmp_path / "data" / "edge-agent.sqlite3")
    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_auth_users").fetchone()[0] == 0


def test_migration_removes_legacy_device_auth_rows(tmp_path):
    database = EdgeDatabase(tmp_path / "edge.sqlite3")
    with database.connection() as connection:
        connection.execute(
            """CREATE TABLE local_auth_users(
                central_user_id TEXT PRIMARY KEY, carnet TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL, local_verifier TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                last_online_auth_at TEXT NOT NULL)"""
        )
        connection.execute(
            "INSERT INTO local_auth_users VALUES(?,?,?,?,?,?,?)",
            ("legacy", "device", "DISPOSITIVO", "legacy", "now", "now", "now"),
        )
    database.initialize()
    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_auth_users").fetchone()[0] == 0


def test_configuration_payload_is_url_only_and_preserves_device_id(tmp_path):
    store = ProductConfigStore(tmp_path)
    store.save("https://old.example", "device-existing")
    store.save("https://new.example")
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 2,
        "central_url": "https://new.example",
        "installation_id": None,
        "installation_provisioned": False,
        "device_id": "device-existing",
    }
