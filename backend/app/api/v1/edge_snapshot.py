from datetime import datetime, timezone

from app.api.v1.auth import require_admin
from app.db.models import Dispositivo, Usuario, Vehiculo
from app.db.session import get_db
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()


def _device_direction(name: str) -> str:
    normalized = name.lower()
    if "entrada" in normalized or "ingreso" in normalized:
        return "ENTRY"
    if "salida" in normalized or "egreso" in normalized:
        return "EXIT"
    return "AUTO"


@router.get("")
async def get_edge_snapshot(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    generated_at = datetime.now(timezone.utc).isoformat()
    vehicles = list(
        (
            await db.execute(
                select(Vehiculo).options(
                    selectinload(Vehiculo.propietario),
                    selectinload(Vehiculo.marca),
                    selectinload(Vehiculo.tipo),
                )
            )
        )
        .scalars()
        .all()
    )
    devices = list((await db.execute(select(Dispositivo))).scalars().all())
    return {
        "version": generated_at,
        "generated_at": generated_at,
        "vehicles": [
            {
                "central_id": str(vehicle.id),
                "plate": vehicle.placa,
                "is_active": vehicle.esta_activo,
                "owner_name": (
                    f"{vehicle.propietario.nombre} {vehicle.propietario.apellido_paterno}".strip()
                    if vehicle.propietario
                    else None
                ),
                "brand_name": vehicle.marca.nombre if vehicle.marca else None,
                "vehicle_type_name": vehicle.tipo.nombre if vehicle.tipo else None,
                "color": vehicle.color,
                "source_updated_at": vehicle.actualizado_el.isoformat(),
            }
            for vehicle in vehicles
        ],
        "devices": [
            {
                "central_id": str(device.id),
                "name": device.nombre,
                "location": device.ubicacion,
                "direction": _device_direction(device.nombre),
                "is_active": device.esta_activo,
                "source_updated_at": device.actualizado_el.isoformat(),
            }
            for device in devices
        ],
    }
