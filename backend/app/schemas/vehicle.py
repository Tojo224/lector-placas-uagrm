from datetime import datetime
from uuid import UUID

from app.ai.validators import normalize_plate_text, validate_bolivian_plate
from app.schemas.auth import UsuarioResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarcaResponse(BaseModel):
    id: UUID
    nombre: str
    creado_el: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TipoVehiculoResponse(BaseModel):
    id: UUID
    nombre: str
    esta_activo: bool = True
    creado_el: datetime

    model_config = ConfigDict(from_attributes=True)


class MarcaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class TipoVehiculoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class VehiculoBase(BaseModel):
    placa: str = Field(min_length=5, max_length=20)
    color: str = Field(min_length=1, max_length=100)
    color_hex: str | None = None
    marca_id: UUID
    tipo_vehiculo_id: UUID
    propietario_usuario_id: UUID

    @field_validator("placa")
    @classmethod
    def validate_license_plate(cls, value: str) -> str:
        normalized = normalize_plate_text(value)
        if not validate_bolivian_plate(normalized):
            raise ValueError("La placa debe tener el formato boliviano NNNNLLL.")
        return normalized


class VehiculoCreate(VehiculoBase):
    pass


class VehiculoResponse(VehiculoBase):
    id: UUID
    esta_activo: bool
    foto_id: UUID | None = None
    creado_el: datetime
    actualizado_el: datetime
    marca: MarcaResponse | None = None
    tipo: TipoVehiculoResponse | None = None
    propietario: UsuarioResponse | None = None

    model_config = ConfigDict(from_attributes=True)
