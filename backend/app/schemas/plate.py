from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator
from app.db.models import EstadoEscaneoEnum


class EscaneadoResponse(BaseModel):
    id: UUID
    ruta_imagen: Optional[str] = None
    placa_detectada: Optional[str] = None
    placa_normalizada: Optional[str] = None
    confianza: Optional[float] = None
    estado: EstadoEscaneoEnum
    dispositivo_id: Optional[UUID] = None
    vehiculo_id: Optional[UUID] = None
    creado_el: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("creado_el", mode="after")
    @classmethod
    def ensure_timezone(cls, v: datetime) -> datetime:
        from datetime import timezone
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class PlateAnalysisResponse(BaseModel):
    estado: str  # DETECTADO | BAJA_CONFIANZA | ERROR | MANUAL
    placa_detectada: Optional[str] = None
    placa_normalizada: Optional[str] = None
    es_formato_valido: bool = False
    confianza: Optional[float] = None
    ruta_imagen: Optional[str] = None
    mensaje: Optional[str] = None
    plate_bbox: Optional[list[float]] = None
    raw_bboxes: Optional[list[list[float]]] = None
    solicitud_id: Optional[UUID] = None
    vehiculo_id: Optional[UUID] = None
    acceso_id: Optional[UUID] = None
    tipo_acceso: Optional[str] = None  # ENTRADA | SALIDA
    es_registrado: bool = False
    propietario_nombre: Optional[str] = None
    marca_sugerida: Optional[str] = None
    tipo_sugerido: Optional[str] = None
    color_sugerido: Optional[str] = None

