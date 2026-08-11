from datetime import datetime
from uuid import UUID

from app.db.models import SolicitudRegistroEstadoEnum
from app.schemas.vehicle import TipoVehiculoResponse
from pydantic import BaseModel, ConfigDict, Field


class SolicitudRegistroResponse(BaseModel):
    id: UUID
    escaneado_id: UUID
    imagen_id: UUID
    placa_sugerida: str
    confianza_placa: float
    color_sugerido: str | None = None
    color_hex: str | None = None
    confianza_color: float | None = None
    metodo_color: str | None = None
    tipo_sugerido_id: UUID | None = None
    confianza_tipo: float | None = None
    metodo_tipo: str | None = None
    tipo_sugerido: TipoVehiculoResponse | None = None
    estado: SolicitudRegistroEstadoEnum
    creado_por_usuario_id: UUID
    revisado_por_usuario_id: UUID | None = None
    vehiculo_creado_id: UUID | None = None
    creado_el: datetime
    revisado_el: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

class SolicitudRegistroApprove(BaseModel):
    placa: str | None = None
    propietario_usuario_id: UUID
    marca_id: UUID
    tipo_vehiculo_id: UUID
    color: str = Field(min_length=1, max_length=100)
    color_hex: str | None = None

class SolicitudRegistroReject(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)
