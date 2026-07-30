import uuid

from app.api.v1.auth import require_admin
from app.db.models import Dispositivo, TipoDispositivo, Usuario
from app.db.session import get_db
from app.schemas.camera import CameraStatus
from app.schemas.device import (
    DispositivoCreate,
    DispositivoResponse,
    DispositivoUpdate,
    TipoDispositivoCreate,
    TipoDispositivoResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

router = APIRouter()


@router.get("/health", response_model=CameraStatus)
async def camera_health(request: Request):
    watchdog = getattr(request.app.state, "camera_watchdog", None)
    if watchdog is None:
        return CameraStatus(alive=False, start_count=0)
    watchdog.ensure_alive()
    health = watchdog.health()
    return CameraStatus(**health)


# ── TIPOS DE DISPOSITIVOS ──────────────────────────────────────────

@router.get("/types", response_model=list[TipoDispositivoResponse])
async def list_device_types(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(TipoDispositivo).order_by(TipoDispositivo.nombre))
    return list(result.scalars().all())


@router.post("/types", response_model=TipoDispositivoResponse, status_code=status.HTTP_201_CREATED)
async def create_device_type(
    type_in: TipoDispositivoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    new_type = TipoDispositivo(nombre=type_in.nombre.strip())
    db.add(new_type)
    try:
        await db.commit()
        await db.refresh(new_type)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Este tipo de dispositivo ya existe.")
    return new_type


@router.put("/types/{type_id}", response_model=TipoDispositivoResponse)
async def update_device_type(
    type_id: uuid.UUID,
    type_in: TipoDispositivoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(TipoDispositivo).where(TipoDispositivo.id == type_id))
    db_type = result.scalars().first()
    if not db_type:
        raise HTTPException(status_code=404, detail="Tipo de dispositivo no encontrado.")
    db_type.nombre = type_in.nombre.strip()
    try:
        await db.commit()
        await db.refresh(db_type)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="El nombre del tipo de dispositivo ya está registrado.")
    return db_type


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_type(
    type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(TipoDispositivo).where(TipoDispositivo.id == type_id))
    db_type = result.scalars().first()
    if not db_type:
        raise HTTPException(status_code=404, detail="Tipo de dispositivo no encontrado.")
    await db.delete(db_type)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── DISPOSITIVOS ──────────────────────────────────────────────────

@router.get("/", response_model=list[DispositivoResponse])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(
        select(Dispositivo)
        .options(selectinload(Dispositivo.tipo))
        .order_by(Dispositivo.nombre)
    )
    return list(result.scalars().all())


@router.post("/", response_model=DispositivoResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_in: DispositivoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    # Validar tipo de dispositivo
    type_result = await db.execute(select(TipoDispositivo).where(TipoDispositivo.id == device_in.tipo_dispositivo_id))
    if not type_result.scalars().first():
        raise HTTPException(status_code=400, detail="El tipo de dispositivo especificado no existe.")

    new_device = Dispositivo(
        nombre=device_in.nombre.strip(),
        ubicacion=device_in.ubicacion.strip(),
        tipo_dispositivo_id=device_in.tipo_dispositivo_id,
        esta_activo=device_in.esta_activo,
        webhook_url=device_in.webhook_url,
    )
    db.add(new_device)
    try:
        await db.commit()
        await db.refresh(new_device)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe un dispositivo con este nombre.")
    
    # Recargar con relaciones
    stmt = select(Dispositivo).options(selectinload(Dispositivo.tipo)).where(Dispositivo.id == new_device.id)
    res = await db.execute(stmt)
    return res.scalars().first()


@router.get("/{device_id}", response_model=DispositivoResponse)
async def get_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(
        select(Dispositivo)
        .options(selectinload(Dispositivo.tipo))
        .where(Dispositivo.id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    return device


@router.put("/{device_id}", response_model=DispositivoResponse)
async def update_device(
    device_id: uuid.UUID,
    device_in: DispositivoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(Dispositivo).where(Dispositivo.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

    if device_in.nombre is not None:
        device.nombre = device_in.nombre.strip()
    if device_in.ubicacion is not None:
        device.ubicacion = device_in.ubicacion.strip()
    if device_in.tipo_dispositivo_id is not None:
        type_result = await db.execute(select(TipoDispositivo).where(TipoDispositivo.id == device_in.tipo_dispositivo_id))
        if not type_result.scalars().first():
            raise HTTPException(status_code=400, detail="El tipo de dispositivo especificado no existe.")
        device.tipo_dispositivo_id = device_in.tipo_dispositivo_id
    if device_in.esta_activo is not None:
        device.esta_activo = device_in.esta_activo
    if "webhook_url" in device_in.model_fields_set:
        device.webhook_url = device_in.webhook_url

    try:
        await db.commit()
        await db.refresh(device)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe un dispositivo registrado con ese nombre.")

    # Recargar con relaciones
    stmt = select(Dispositivo).options(selectinload(Dispositivo.tipo)).where(Dispositivo.id == device.id)
    res = await db.execute(stmt)
    return res.scalars().first()


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(Dispositivo).where(Dispositivo.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    await db.delete(device)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
