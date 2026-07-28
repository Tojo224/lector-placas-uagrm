from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.db.models import SolicitudRegistroEstadoEnum

class SolicitudRegistroResponse(BaseModel):
    id: UUID
    escaneado_id: UUID
    imagen_id: UUID
    placa_sugerida: str
    confianza_placa: float
    color_sugerido: str | None = None
    confianza_color: float | None = None
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

class SolicitudRegistroReject(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)
