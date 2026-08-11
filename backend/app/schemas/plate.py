from datetime import datetime
from uuid import UUID

from app.db.models import EstadoEscaneoEnum
from pydantic import BaseModel, ConfigDict, field_validator


class EscaneadoResponse(BaseModel):
    id: UUID
    ruta_imagen: str | None = None
    placa_detectada: str | None = None
    placa_normalizada: str | None = None
    confianza: float | None = None
    estado: EstadoEscaneoEnum
    dispositivo_id: UUID | None = None
    vehiculo_id: UUID | None = None
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
    placa_detectada: str | None = None
    placa_normalizada: str | None = None
    es_formato_valido: bool = False
    confianza: float | None = None
    ruta_imagen: str | None = None
    mensaje: str | None = None
    plate_bbox: list[float] | None = None
    raw_bboxes: list[list[float]] | None = None
    solicitud_id: UUID | None = None
    vehiculo_id: UUID | None = None
    acceso_id: UUID | None = None
    tipo_acceso: str | None = None  # ENTRADA | SALIDA
    es_registrado: bool = False
    propietario_nombre: str | None = None
    color_sugerido: str | None = None
    color_hex: str | None = None
    confianza_color: float | None = None
    metodo_color: str | None = None
    tipo_sugerido_id: UUID | None = None
    tipo_sugerido: str | None = None
    confianza_tipo: float | None = None
    metodo_tipo: str | None = None

