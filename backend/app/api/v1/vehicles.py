import uuid

from app.api.v1.auth import get_current_user, require_admin
from app.db.models import Marca, RoleEnum, TipoVehiculo, Usuario, Vehiculo
from app.db.session import get_db
from app.schemas.vehicle import VehiculoCreate, VehiculoResponse
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

router = APIRouter()


async def get_vehicle_with_relations(vehicle_id: uuid.UUID, db: AsyncSession):
    result = await db.execute(
        select(Vehiculo)
        .options(
            selectinload(Vehiculo.propietario),
            selectinload(Vehiculo.marca),
            selectinload(Vehiculo.tipo),
        )
        .where(Vehiculo.id == vehicle_id)
    )
    return result.scalars().first()


@router.get("/", response_model=list[VehiculoResponse])
async def list_vehicles(
    propietario_usuario_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Vehiculo).options(
        selectinload(Vehiculo.propietario),
        selectinload(Vehiculo.marca),
        selectinload(Vehiculo.tipo)
    ).order_by(Vehiculo.creado_el.desc())

    if propietario_usuario_id:
        query = query.where(Vehiculo.propietario_usuario_id == propietario_usuario_id)
    
    # Solo los usuarios regulares ven únicamente sus propios vehículos
    if current_user.rol not in [RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR, RoleEnum.DISPOSITIVO]:
        query = query.where(Vehiculo.propietario_usuario_id == current_user.id)
        
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/by-plate/{plate}", response_model=VehiculoResponse)
async def get_vehicle_by_plate(plate: str, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    plate = plate.upper().strip()
    result = await db.execute(
        select(Vehiculo)
        .options(
            selectinload(Vehiculo.propietario),
            selectinload(Vehiculo.marca),
            selectinload(Vehiculo.tipo)
        )
        .where(Vehiculo.placa == plate)
    )
    vehicle = result.scalars().first()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehículo no registrado.",
        )
    if (
        current_user.rol not in {RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR}
        and vehicle.propietario_usuario_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="No autorizado")
    return vehicle


from app.schemas.vehicle import (
    MarcaCreate,
    MarcaResponse,
    TipoVehiculoCreate,
    TipoVehiculoResponse,
    VehiculoResponse,
)

# ...

@router.get("/brands", response_model=list[MarcaResponse])
async def list_brands(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    result = await db.execute(select(Marca).order_by(Marca.nombre))
    return list(result.scalars().all())


@router.post("/brands", response_model=MarcaResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    brand_in: MarcaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    new_brand = Marca(nombre=brand_in.nombre.strip())
    db.add(new_brand)
    try:
        await db.commit()
        await db.refresh(new_brand)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Esta marca ya se encuentra registrada.")
    return new_brand


@router.put("/brands/{brand_id}", response_model=MarcaResponse)
async def update_brand(
    brand_id: uuid.UUID,
    brand_in: MarcaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(Marca).where(Marca.id == brand_id))
    brand = result.scalars().first()
    if not brand:
        raise HTTPException(status_code=404, detail="Marca no encontrada.")
    brand.nombre = brand_in.nombre.strip()
    try:
        await db.commit()
        await db.refresh(brand)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Ese nombre de marca ya está registrado.")
    return brand


@router.delete("/brands/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(Marca).where(Marca.id == brand_id))
    brand = result.scalars().first()
    if not brand:
        raise HTTPException(status_code=404, detail="Marca no encontrada.")
    await db.delete(brand)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/types", response_model=list[TipoVehiculoResponse])
async def list_vehicle_types(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    result = await db.execute(
        select(TipoVehiculo).where(TipoVehiculo.esta_activo.is_(True)).order_by(TipoVehiculo.nombre)
    )
    return list(result.scalars().all())


@router.post("/types", response_model=TipoVehiculoResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle_type(
    type_in: TipoVehiculoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    new_type = TipoVehiculo(nombre=type_in.nombre.strip())
    db.add(new_type)
    try:
        await db.commit()
        await db.refresh(new_type)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Este tipo de vehículo ya se encuentra registrado.")
    return new_type


@router.put("/types/{type_id}", response_model=TipoVehiculoResponse)
async def update_vehicle_type(
    type_id: uuid.UUID,
    type_in: TipoVehiculoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(TipoVehiculo).where(TipoVehiculo.id == type_id))
    v_type = result.scalars().first()
    if not v_type:
        raise HTTPException(status_code=404, detail="Tipo de vehículo no encontrado.")
    v_type.nombre = type_in.nombre.strip()
    try:
        await db.commit()
        await db.refresh(v_type)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Ese nombre de tipo de vehículo ya está registrado.")
    return v_type


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle_type(
    type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(select(TipoVehiculo).where(TipoVehiculo.id == type_id))
    v_type = result.scalars().first()
    if not v_type:
        raise HTTPException(status_code=404, detail="Tipo de vehículo no encontrado.")
    # Se desactiva en lugar de borrar: las sugerencias históricas conservan su
    # relación, pero el tipo deja de participar en catálogos y nuevos análisis.
    v_type.esta_activo = False
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{vehicle_id}", response_model=VehiculoResponse)
async def get_vehicle_detail(vehicle_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    vehicle = await get_vehicle_with_relations(vehicle_id, db)
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehículo no encontrado.",
        )
    if (
        current_user.rol not in [RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR]
        and vehicle.propietario_usuario_id != current_user.id
    ):
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para ver los detalles de este vehículo.",
        )
    return vehicle


@router.post("/", response_model=VehiculoResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(vehicle_in: VehiculoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if current_user.rol == RoleEnum.DISPOSITIVO:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    # Validar propietario, marca y tipo (secuencial: AsyncSession no es thread-safe para concurrente)
    owner_res = await db.execute(select(Usuario).where(Usuario.id == vehicle_in.propietario_usuario_id))
    marca_res = await db.execute(select(Marca).where(Marca.id == vehicle_in.marca_id))
    tipo_res = await db.execute(select(TipoVehiculo).where(TipoVehiculo.id == vehicle_in.tipo_vehiculo_id))
    owner = owner_res.scalars().first()
    if not owner or not owner.esta_activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden registrar vehículos a nombre de una persona inactiva o inexistente.",
        )

    # Solo el rol USUARIO puede poseer vehículos en el sistema
    if owner.rol != RoleEnum.USUARIO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los vehículos solo pueden ser registrados a nombre de usuarios regulares (estudiantes/docentes). Administradores u operadores no pueden poseer vehículos.",
        )

    if current_user.rol in [RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR]:
        if vehicle_in.propietario_usuario_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Los administradores y operadores no pueden registrar vehículos a su propio nombre.",
            )
    else:
        if vehicle_in.propietario_usuario_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes registrar vehículos a tu propio nombre.",
            )

    if not marca_res.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Marca inválida.")
    if not tipo_res.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de vehículo inválido.")

    new_vehicle = Vehiculo(
        placa=vehicle_in.placa.upper().strip(),
        color=vehicle_in.color.strip(),
        color_hex=vehicle_in.color_hex,
        marca_id=vehicle_in.marca_id,
        tipo_vehiculo_id=vehicle_in.tipo_vehiculo_id,
        propietario_usuario_id=vehicle_in.propietario_usuario_id,
        esta_activo=True
    )
    db.add(new_vehicle)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta placa ya se encuentra registrada en el sistema.",
        )

    return await get_vehicle_with_relations(new_vehicle.id, db)


@router.put("/{vehicle_id}", response_model=VehiculoResponse)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    vehicle_in: VehiculoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    vehicle = await get_vehicle_with_relations(vehicle_id, db)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehículo no encontrado.")

    if (
        current_user.rol not in [RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR]
        and vehicle.propietario_usuario_id != current_user.id
    ):
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para actualizar este vehículo.",
        )

    owner_result = await db.execute(select(Usuario).where(Usuario.id == vehicle_in.propietario_usuario_id))
    owner = owner_result.scalars().first()
    if not owner or not owner.esta_activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden registrar vehículos a nombre de una persona inactiva o inexistente.",
        )

    # Solo el rol USUARIO puede poseer vehículos en el sistema
    if owner.rol != RoleEnum.USUARIO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los vehículos solo pueden estar a nombre de usuarios regulares. Administradores u operadores no pueden poseer vehículos.",
        )

    # El personal no puede asignarse vehículos a sí mismo
    if current_user.rol in [RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR]:
        if vehicle_in.propietario_usuario_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Los administradores y operadores no pueden registrar vehículos a su propio nombre.",
            )
    else:
        if vehicle_in.propietario_usuario_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puedes cambiar el propietario de este vehículo.",
            )

    vehicle.placa = vehicle_in.placa.upper().strip()
    vehicle.color = vehicle_in.color.strip()
    vehicle.marca_id = vehicle_in.marca_id
    vehicle.tipo_vehiculo_id = vehicle_in.tipo_vehiculo_id
    vehicle.propietario_usuario_id = vehicle_in.propietario_usuario_id

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error al actualizar (posible placa duplicada).",
        )

    return await get_vehicle_with_relations(vehicle.id, db)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(
    vehicle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    vehicle = await get_vehicle_with_relations(vehicle_id, db)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehículo no encontrado.")

    if (
        current_user.rol not in [RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR]
        and vehicle.propietario_usuario_id != current_user.id
    ):
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para eliminar este vehículo.",
        )

    from app.db.models import EstadoCampus, Escaneado, SolicitudRegistroVehiculo
    from sqlalchemy import update, delete

    # 1. Eliminar el estado del campus asociado
    await db.execute(
        delete(EstadoCampus).where(EstadoCampus.vehiculo_id == vehicle_id)
    )

    # 2. Desasociar los registros de escaneo
    await db.execute(
        update(Escaneado)
        .where(Escaneado.vehiculo_id == vehicle_id)
        .values(vehiculo_id=None)
    )

    # 3. Desasociar solicitudes de registro de vehículos
    await db.execute(
        update(SolicitudRegistroVehiculo)
        .where(SolicitudRegistroVehiculo.vehiculo_creado_id == vehicle_id)
        .values(vehiculo_creado_id=None)
    )

    await db.delete(vehicle)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

