from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from app.api.v1.auth import require_admin
from app.core.security import hash_password, verify_password
from app.db.models import (
    Acceso,
    Dispositivo,
    Escaneado,
    EstadoEscaneoEnum,
    TipoAccesoEnum,
    Usuario,
    Vehiculo,
)
from app.db.session import get_db
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()


class EdgeEvent(BaseModel):
    event_id: UUID
    event_type: Literal["SCAN_RECORDED", "ACCESS_DECIDED"]
    schema_version: int = 1
    payload: dict[str, Any]


class EdgeBatch(BaseModel):
    events: list[EdgeEvent] = Field(max_length=100)


async def require_edge_device(
    x_edge_device_id: UUID = Header(),
    authorization: str = Header(),
    db: AsyncSession = Depends(get_db),
) -> Dispositivo:
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Credencial Edge invalida.")
    device = await db.get(Dispositivo, x_edge_device_id)
    key = authorization[len(prefix):]
    if (
        not device
        or not device.esta_activo
        or not device.edge_credential_hash
        or not verify_password(key, device.edge_credential_hash)
    ):
        raise HTTPException(status_code=401, detail="Credencial Edge invalida.")
    return device


@router.post("/devices/{device_id}/provision")
async def provision_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_admin),
):
    device = await db.get(Dispositivo, device_id)
    if not device or not device.esta_activo:
        raise HTTPException(status_code=404, detail="Dispositivo activo no encontrado.")
    credential = secrets.token_urlsafe(32)
    device.edge_credential_hash = hash_password(credential)
    device.edge_credential_issued_at = datetime.now(timezone.utc)
    await db.commit()
    return {"device_id": str(device.id), "credential": credential,
            "issued_at": device.edge_credential_issued_at.isoformat()}


@router.get("/snapshot")
async def edge_snapshot(
    db: AsyncSession = Depends(get_db),
    _device: Dispositivo = Depends(require_edge_device),
):
    generated_at = datetime.now(timezone.utc).isoformat()
    vehicles = list((await db.execute(select(Vehiculo).options(
        selectinload(Vehiculo.propietario), selectinload(Vehiculo.marca),
        selectinload(Vehiculo.tipo)))).scalars().all())
    devices = list((await db.execute(select(Dispositivo))).scalars().all())
    return {
        "version": generated_at, "generated_at": generated_at,
        "vehicles": [{"central_id": str(item.id), "plate": item.placa,
                      "is_active": item.esta_activo,
                      "owner_name": (f"{item.propietario.nombre} "
                                     f"{item.propietario.apellido_paterno}".strip()),
                      "brand_name": item.marca.nombre, "vehicle_type_name": item.tipo.nombre,
                      "color": item.color,
                      "source_updated_at": item.actualizado_el.isoformat()}
                     for item in vehicles],
        "devices": [{"central_id": str(item.id), "name": item.nombre,
                     "location": item.ubicacion, "direction": "AUTO",
                     "is_active": item.esta_activo,
                     "source_updated_at": item.actualizado_el.isoformat()}
                    for item in devices],
    }


def _scan_status(value: str) -> EstadoEscaneoEnum:
    return {"DETECTED": EstadoEscaneoEnum.DETECTADO,
            "LOW_CONFIDENCE": EstadoEscaneoEnum.BAJA_CONFIANZA}.get(
                value, EstadoEscaneoEnum.ERROR)


async def _ingest_event(db: AsyncSession, device: Dispositivo,
                        event: EdgeEvent) -> str:
    payload = event.payload
    if event.schema_version != 1:
        return "PERMANENT_ERROR"
    if event.event_type == "SCAN_RECORDED":
        if await db.get(Escaneado, event.event_id):
            return "DUPLICATE"
        db.add(Escaneado(
            id=event.event_id, placa_detectada=payload.get("plate"),
            placa_normalizada=payload.get("plate"),
            confianza=payload.get("confidence"),
            estado=_scan_status(str(payload.get("status", "DETECTED"))),
            dispositivo_id=device.id,
            creado_el=datetime.fromisoformat(payload["captured_at"]),
        ))
        await db.commit()
        return "ACCEPTED"

    access_id = event.event_id
    if await db.get(Acceso, access_id):
        return "DUPLICATE"
    required = {"scan_id", "vehicle_central_id", "direction", "occurred_at"}
    if not required.issubset(payload) or payload["direction"] not in {"ENTRADA", "SALIDA"}:
        return "PERMANENT_ERROR"
    vehicle = await db.get(Vehiculo, UUID(str(payload["vehicle_central_id"])))
    if not vehicle:
        return "PERMANENT_ERROR"
    scan_id = UUID(str(payload["scan_id"]))
    scan = await db.get(Escaneado, scan_id)
    if not scan:
        scan = Escaneado(
            id=scan_id, placa_detectada=vehicle.placa,
            placa_normalizada=vehicle.placa, estado=EstadoEscaneoEnum.DETECTADO,
            dispositivo_id=device.id, vehiculo_id=vehicle.id,
            creado_el=datetime.fromisoformat(payload["occurred_at"]),
        )
        db.add(scan)
        await db.flush()
    db.add(Acceso(
        id=access_id, tipo_acceso=TipoAccesoEnum(payload["direction"]),
        ubicacion=device.ubicacion, escaneado_id=scan_id,
        creado_el=datetime.fromisoformat(payload["occurred_at"]),
    ))
    await db.commit()
    return "ACCEPTED"


@router.post("/events")
async def ingest_events(
    batch: EdgeBatch,
    db: AsyncSession = Depends(get_db),
    device: Dispositivo = Depends(require_edge_device),
):
    results = []
    for event in batch.events:
        try:
            status = await _ingest_event(db, device, event)
        except (ValueError, KeyError):
            await db.rollback()
            status = "PERMANENT_ERROR"
        except SQLAlchemyError:
            await db.rollback()
            status = "RETRYABLE_ERROR"
        results.append({"event_id": str(event.event_id), "status": status})
    return {"results": results}
