from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api.v1.edge_sync import (
    EdgeEvent,
    _ingest_event,
    ingest_media,
    provision_installation,
    provision_device,
)
from app.core.security import verify_password
from app.db.models import (
    Acceso,
    Dispositivo,
    EdgeInstallation,
    Escaneado,
    MediaTypeEnum,
    TipoAccesoEnum,
)
from PIL import Image
from starlette.datastructures import Headers, UploadFile


class MemorySession:
    def __init__(self):
        self.rows = {}

    async def get(self, model, row_id):
        return self.rows.get((model, row_id))

    def add(self, value):
        self.rows[(type(value), value.id)] = value

    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.mark.anyio
async def test_provision_returns_device_credential_once_and_stores_only_hash():
    session = MemorySession()
    device = Dispositivo(id=uuid4(), nombre="Porton", ubicacion="Campus",
                         tipo_dispositivo_id=uuid4(), esta_activo=True)
    session.rows[(Dispositivo, device.id)] = device
    result = await provision_device(device.id, session, None)
    assert result["credential"] != device.edge_credential_hash
    assert verify_password(result["credential"], device.edge_credential_hash)


@pytest.mark.anyio
async def test_staff_login_provisions_independent_installation_credential():
    session = MemorySession()
    installation_id = uuid4()
    result = await provision_installation(
        SimpleNamespace(installation_id=installation_id), session, None
    )
    installation = session.rows[(EdgeInstallation, installation_id)]
    assert result["installation_id"] == str(installation_id)
    assert result["credential"] != installation.credential_hash
    assert verify_password(result["credential"], installation.credential_hash)
    assert installation.is_active is True


@pytest.mark.anyio
async def test_installation_scan_ingestion_does_not_require_functional_device():
    session = MemorySession()
    event_id = uuid4()
    event = EdgeEvent(
        event_id=event_id, event_type="SCAN_RECORDED", schema_version=1,
        payload={"plate": "9999ZZZ", "status": "DETECTED", "confidence": 0.9,
                 "captured_at": datetime.now(timezone.utc).isoformat()},
    )
    assert await _ingest_event(session, None, event) == "ACCEPTED"
    scan = session.rows[(Escaneado, event_id)]
    assert scan.dispositivo_id is None


@pytest.mark.anyio
async def test_central_scan_ingestion_is_idempotent():
    session = MemorySession()
    event_id = uuid4()
    device = Dispositivo(id=uuid4(), nombre="Porton", ubicacion="Campus",
                         tipo_dispositivo_id=uuid4(), esta_activo=True)
    event = EdgeEvent(
        event_id=event_id, event_type="SCAN_RECORDED", schema_version=1,
        payload={"plate": "9999ZZZ", "status": "DETECTED", "confidence": 0.9,
                 "captured_at": datetime.now(timezone.utc).isoformat()},
    )
    assert await _ingest_event(session, device, event) == "ACCEPTED"
    assert await _ingest_event(session, device, event) == "DUPLICATE"
    assert len([key for key in session.rows if key[0] is Escaneado]) == 1


@pytest.mark.anyio
async def test_unknown_event_schema_is_permanent_error():
    session = MemorySession()
    device = Dispositivo(id=uuid4(), nombre="Porton", ubicacion="Campus",
                         tipo_dispositivo_id=uuid4(), esta_activo=True)
    event = EdgeEvent(event_id=uuid4(), event_type="SCAN_RECORDED",
                      schema_version=99, payload={})
    assert await _ingest_event(session, device, event) == "PERMANENT_ERROR"


@pytest.mark.anyio
async def test_central_media_upload_is_idempotent(monkeypatch):
    session = MemorySession()
    scan_id, access_id, media_id = uuid4(), uuid4(), uuid4()
    scan = Escaneado(id=scan_id, estado="DETECTADO", creado_el=datetime.now(timezone.utc))
    access = Acceso(id=access_id, tipo_acceso=TipoAccesoEnum.ENTRADA,
                    ubicacion="Campus", escaneado_id=scan_id)
    session.rows[(Escaneado, scan_id)] = scan
    session.rows[(Acceso, access_id)] = access
    output = BytesIO()
    Image.new("RGB", (20, 10), "navy").save(output, format="WEBP")
    content = output.getvalue()
    uploads = []

    class Storage:
        def upload(self, data, media_type, public_id):
            uploads.append((data, media_type, public_id))
            return SimpleNamespace(asset_id="asset", public_id=public_id,
                resource_type="image", delivery_type="authenticated", format="webp",
                width=20, height=10, bytes=len(data))

    monkeypatch.setattr("app.api.v1.edge_sync.CloudinaryStorage", Storage)

    def upload_file():
        return UploadFile(BytesIO(content), filename="evidence.webp",
                          headers=Headers({"content-type": "image/webp"}))

    kwargs = {"media_id": media_id, "media_type": MediaTypeEnum.ACCESS_ENTRY,
              "checksum_sha256": hashlib.sha256(content).hexdigest(),
              "size_bytes": len(content), "schema_version": 1,
              "scan_id": scan_id, "access_event_id": access_id,
              "db": session, "_device": None}
    first = await ingest_media(file=upload_file(), **kwargs)
    second = await ingest_media(file=upload_file(), **kwargs)
    assert first["status"] == "ACCEPTED"
    assert second["status"] == "DUPLICATE"
    assert len(uploads) == 1
    assert uploads[0][2] == f"edge-{media_id}"
