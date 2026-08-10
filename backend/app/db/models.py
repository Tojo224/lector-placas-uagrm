import enum
import uuid
from datetime import datetime, timezone

from app.db.session import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid


class RoleEnum(str, enum.Enum):
    ADMINISTRADOR = "ADMINISTRADOR"
    OPERADOR = "OPERADOR"
    DISPOSITIVO = "DISPOSITIVO"
    USUARIO = "USUARIO"


class RecordStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class TipoAccesoEnum(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"


class EstadoEscaneoEnum(str, enum.Enum):
    DETECTADO = "DETECTADO"
    BAJA_CONFIANZA = "BAJA_CONFIANZA"
    ERROR = "ERROR"
    MANUAL = "MANUAL"


class UbicacionVehiculoEnum(str, enum.Enum):
    DENTRO = "DENTRO"
    FUERA = "FUERA"


class MediaProviderEnum(str, enum.Enum):
    CLOUDINARY = "CLOUDINARY"


class MediaTypeEnum(str, enum.Enum):
    USER_PROFILE = "USER_PROFILE"
    VEHICLE_REGISTRATION = "VEHICLE_REGISTRATION"
    ACCESS_ENTRY = "ACCESS_ENTRY"
    ACCESS_EXIT = "ACCESS_EXIT"


class MediaStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    DELETED = "DELETED"


class SolicitudRegistroEstadoEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre = Column(String, nullable=False)
    apellido_paterno = Column(String, nullable=False)
    apellido_materno = Column(String, nullable=True)
    carnet = Column(String, unique=True, index=True, nullable=False)
    contrasena_hash = Column(String, nullable=False)
    rol = Column(Enum(RoleEnum), default=RoleEnum.USUARIO, nullable=False, index=True)
    esta_activo = Column(Boolean, default=True, nullable=False, index=True)
    foto_id = Column(Uuid, ForeignKey("archivos_multimedia.id"), nullable=True)
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    actualizado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    vehiculos = relationship("Vehiculo", back_populates="propietario")
    accesos_gestionados = relationship("Acceso", back_populates="operador")
    foto = relationship("ArchivoMultimedia", foreign_keys=[foto_id])


class Marca(Base):
    __tablename__ = "marcas"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre = Column(String, unique=True, nullable=False)
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class TipoVehiculo(Base):
    __tablename__ = "tipos_vehiculo"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre = Column(String, unique=True, nullable=False)
    esta_activo = Column(Boolean, default=True, nullable=False, index=True)
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Vehiculo(Base):
    __tablename__ = "vehiculos"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    placa = Column(String, unique=True, index=True, nullable=False)
    color = Column(String, nullable=False)
    marca_id = Column(Uuid, ForeignKey("marcas.id"), nullable=False, index=True)
    tipo_vehiculo_id = Column(Uuid, ForeignKey("tipos_vehiculo.id"), nullable=False, index=True)
    propietario_usuario_id = Column(Uuid, ForeignKey("usuarios.id"), nullable=False, index=True)
    esta_activo = Column(Boolean, default=True, nullable=False, index=True)
    foto_id = Column(Uuid, ForeignKey("archivos_multimedia.id"), nullable=True)
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    actualizado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    marca = relationship("Marca")
    tipo = relationship("TipoVehiculo")
    propietario = relationship("Usuario", back_populates="vehiculos")
    escaneos = relationship("Escaneado", back_populates="vehiculo")
    estado_campus = relationship("EstadoCampus", back_populates="vehiculo", uselist=False)
    foto = relationship("ArchivoMultimedia", foreign_keys=[foto_id])


class EstadoCampus(Base):
    __tablename__ = "estado_campus"
    __table_args__ = (
        UniqueConstraint("vehiculo_id", name="estado_campus_vehiculo_id_key"),
        Index("ix_estado_campus_vehiculo_id", "vehiculo_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    vehiculo_id = Column(Uuid, ForeignKey("vehiculos.id"), nullable=False)
    estado = Column(Enum(UbicacionVehiculoEnum), nullable=False)
    ultimo_acceso_id = Column(Uuid, ForeignKey("accesos.id"), nullable=False)
    actualizado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)

    vehiculo = relationship("Vehiculo", back_populates="estado_campus")
    ultimo_acceso = relationship("Acceso", foreign_keys=[ultimo_acceso_id])


class TipoDispositivo(Base):
    __tablename__ = "tipos_dispositivo"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre = Column(String, nullable=False) # E.g. "Entrada", "Salida"
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre = Column(String, nullable=False)
    ubicacion = Column(String, nullable=False)
    tipo_dispositivo_id = Column(Uuid, ForeignKey("tipos_dispositivo.id"), nullable=False)
    esta_activo = Column(Boolean, default=True, nullable=False)
    webhook_url = Column(String, nullable=True)  # URL del actuador de barrera (simulador o ESP32)
    edge_credential_hash = Column(String, nullable=True)
    edge_credential_issued_at = Column(DateTime(timezone=True), nullable=True)
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    actualizado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tipo = relationship("TipoDispositivo")
    escaneos = relationship("Escaneado", back_populates="dispositivo")


class EdgeInstallation(Base):
    __tablename__ = "edge_installations"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    credential_hash = Column(String, nullable=False)
    credential_issued_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )


class Escaneado(Base):
    __tablename__ = "escaneados"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    ruta_imagen = Column(String, nullable=True)
    placa_detectada = Column(String, nullable=True)
    placa_normalizada = Column(String, index=True, nullable=True)
    confianza = Column(Float, nullable=True)
    estado = Column(Enum(EstadoEscaneoEnum), nullable=False, default=EstadoEscaneoEnum.DETECTADO)
    dispositivo_id = Column(Uuid, ForeignKey("dispositivos.id"), nullable=True, index=True)
    vehiculo_id = Column(Uuid, ForeignKey("vehiculos.id"), nullable=True, index=True)
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)

    dispositivo = relationship("Dispositivo", back_populates="escaneos")
    vehiculo = relationship("Vehiculo", back_populates="escaneos")
    acceso = relationship("Acceso", back_populates="escaneado", uselist=False)
    acceso_visitante = relationship("AccesoVisitante", back_populates="escaneado", uselist=False)


class AccesoVisitante(Base):
    __tablename__ = "accesos_visitantes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre_conductor = Column(String, nullable=False)
    carnet_conductor = Column(String, index=True, nullable=False)
    motivo = Column(String, nullable=True)
    institucion_empresa = Column(String, nullable=True)
    escaneado_id = Column(Uuid, ForeignKey("escaneados.id"), nullable=False)

    escaneado = relationship("Escaneado", back_populates="acceso_visitante")


class Acceso(Base):
    __tablename__ = "accesos"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo_acceso = Column(Enum(TipoAccesoEnum), nullable=False, index=True)
    ubicacion = Column(String, nullable=False)
    escaneado_id = Column(Uuid, ForeignKey("escaneados.id"), nullable=False, index=True)
    operador_usuario_id = Column(Uuid, ForeignKey("usuarios.id"), nullable=True, index=True)
    imagen_id = Column(Uuid, ForeignKey("archivos_multimedia.id"), nullable=True)
    creado_el = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)

    escaneado = relationship("Escaneado", back_populates="acceso")
    operador = relationship("Usuario", back_populates="accesos_gestionados")
    imagen = relationship("ArchivoMultimedia", foreign_keys=[imagen_id])


class ArchivoMultimedia(Base):
    __tablename__ = "archivos_multimedia"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    proveedor = Column(Enum(MediaProviderEnum), nullable=False, default=MediaProviderEnum.CLOUDINARY)
    tipo = Column(Enum(MediaTypeEnum), nullable=False)
    estado = Column(Enum(MediaStatusEnum), nullable=False, default=MediaStatusEnum.PENDING, index=True)
    asset_id = Column(String, nullable=True, unique=True)
    public_id = Column(String, nullable=True, unique=True)
    resource_type = Column(String, nullable=False, default="image")
    delivery_type = Column(String, nullable=False, default="authenticated")
    formato = Column(String, nullable=True)
    ancho = Column(Integer, nullable=True)
    alto = Column(Integer, nullable=True)
    peso_bytes = Column(Integer, nullable=True)
    intentos = Column(Integer, nullable=False, default=0)
    ultimo_error = Column(Text, nullable=True)
    spool_path = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class SolicitudRegistroVehiculo(Base):
    __tablename__ = "solicitudes_registro_vehiculo"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    escaneado_id = Column(Uuid, ForeignKey("escaneados.id"), nullable=False, unique=True)
    imagen_id = Column(Uuid, ForeignKey("archivos_multimedia.id"), nullable=False)
    placa_sugerida = Column(String, nullable=False, index=True)
    confianza_placa = Column(Float, nullable=False)
    color_sugerido = Column(String, nullable=True)
    confianza_color = Column(Float, nullable=True)
    metodo_color = Column(String, nullable=True)
    tipo_sugerido_id = Column(Uuid, ForeignKey("tipos_vehiculo.id"), nullable=True)
    confianza_tipo = Column(Float, nullable=True)
    metodo_tipo = Column(String, nullable=True)
    estado = Column(Enum(SolicitudRegistroEstadoEnum), nullable=False, default=SolicitudRegistroEstadoEnum.PENDING, index=True)
    creado_por_usuario_id = Column(Uuid, ForeignKey("usuarios.id"), nullable=False)
    revisado_por_usuario_id = Column(Uuid, ForeignKey("usuarios.id"), nullable=True)
    vehiculo_creado_id = Column(Uuid, ForeignKey("vehiculos.id"), nullable=True)
    creado_el = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    revisado_el = Column(DateTime(timezone=True), nullable=True)
    actualizado_el = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    escaneado = relationship("Escaneado")
    imagen = relationship("ArchivoMultimedia")
    creador = relationship("Usuario", foreign_keys=[creado_por_usuario_id])
    revisor = relationship("Usuario", foreign_keys=[revisado_por_usuario_id])
    vehiculo_creado = relationship("Vehiculo", foreign_keys=[vehiculo_creado_id])
    tipo_sugerido = relationship("TipoVehiculo", foreign_keys=[tipo_sugerido_id])
