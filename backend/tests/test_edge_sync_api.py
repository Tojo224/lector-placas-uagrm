from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.api.v1.edge_sync import EdgeEvent, _ingest_event, provision_device
from app.core.security import verify_password
from app.db.models import Dispositivo, Escaneado


class MemorySession:
    def __init__(self):
        self.rows = {}

    async def get(self, model, row_id):
        return self.rows.get((model, row_id))

    def add(self, value):
        self.rows[(type(value), value.id)] = value

    async def commit(self):
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
