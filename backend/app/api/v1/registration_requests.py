from datetime import datetime, timezone
from uuid import UUID

from app.ai.validators import normalize_plate_text, validate_bolivian_plate
from app.api.v1.auth import require_staff
from app.db.models import (
    Marca,
    RoleEnum,
    SolicitudRegistroEstadoEnum,
    SolicitudRegistroVehiculo,
    TipoVehiculo,
    Usuario,
    Vehiculo,
)
from app.db.session import get_db
from app.schemas.registration_request import (
    SolicitudRegistroApprove,
    SolicitudRegistroReject,
    SolicitudRegistroResponse,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()

@router.get("", response_model=list[SolicitudRegistroResponse])
async def list_requests(db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_staff)):
    result = await db.execute(
        select(SolicitudRegistroVehiculo)
        .options(selectinload(SolicitudRegistroVehiculo.tipo_sugerido))
        .order_by(SolicitudRegistroVehiculo.creado_el.desc())
    )
    return list(result.scalars().all())

@router.post("/{request_id}/approve", response_model=SolicitudRegistroResponse)
async def approve_request(request_id: UUID, payload: SolicitudRegistroApprove, db: AsyncSession = Depends(get_db), reviewer: Usuario = Depends(require_staff)):
    request = await db.scalar(
        select(SolicitudRegistroVehiculo)
        .options(selectinload(SolicitudRegistroVehiculo.tipo_sugerido))
        .where(SolicitudRegistroVehiculo.id == request_id)
        .with_for_update()
    )
    if not request: raise HTTPException(404, "Solicitud no encontrada")
    if request.estado != SolicitudRegistroEstadoEnum.PENDING: raise HTTPException(409, "La solicitud ya fue revisada")
    plate = normalize_plate_text(payload.placa or request.placa_sugerida)
    if not validate_bolivian_plate(plate): raise HTTPException(422, "La placa no tiene formato valido")
    if await db.scalar(select(Vehiculo).where(Vehiculo.placa == plate)):
        raise HTTPException(409, "La placa ya esta registrada")
    owner = await db.get(Usuario, payload.propietario_usuario_id)
    if not owner or not owner.esta_activo or owner.rol != RoleEnum.USUARIO:
        raise HTTPException(422, "El propietario debe ser un usuario regular activo")
    if not await db.get(Marca, payload.marca_id): raise HTTPException(422, "Marca no encontrada")
    if not await db.get(TipoVehiculo, payload.tipo_vehiculo_id): raise HTTPException(422, "Tipo de vehiculo no encontrado")
    vehicle = Vehiculo(placa=plate, color=payload.color.strip(), color_hex=payload.color_hex, marca_id=payload.marca_id, tipo_vehiculo_id=payload.tipo_vehiculo_id, propietario_usuario_id=payload.propietario_usuario_id, foto_id=request.imagen_id)
    db.add(vehicle); await db.flush()
    request.estado = SolicitudRegistroEstadoEnum.APPROVED; request.revisado_por_usuario_id = reviewer.id; request.vehiculo_creado_id = vehicle.id; request.revisado_el = datetime.now(timezone.utc)
    request.color_hex = payload.color_hex
    await db.commit(); await db.refresh(request)
    return request

@router.post("/{request_id}/reject", response_model=SolicitudRegistroResponse)
async def reject_request(request_id: UUID, payload: SolicitudRegistroReject, db: AsyncSession = Depends(get_db), reviewer: Usuario = Depends(require_staff)):
    request = await db.scalar(
        select(SolicitudRegistroVehiculo)
        .options(selectinload(SolicitudRegistroVehiculo.tipo_sugerido))
        .where(SolicitudRegistroVehiculo.id == request_id)
        .with_for_update()
    )
    if not request: raise HTTPException(404, "Solicitud no encontrada")
    if request.estado != SolicitudRegistroEstadoEnum.PENDING: raise HTTPException(409, "La solicitud ya fue revisada")
    request.estado = SolicitudRegistroEstadoEnum.REJECTED; request.revisado_por_usuario_id = reviewer.id; request.revisado_el = datetime.now(timezone.utc)
    await db.commit(); await db.refresh(request)
    return request
