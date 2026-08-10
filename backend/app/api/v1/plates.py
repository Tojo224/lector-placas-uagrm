import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from time import perf_counter

from app.ai.pipeline import get_pipeline_status
from app.ai.validators import validate_bolivian_plate
from app.api.v1.auth import require_scanner, require_staff
from app.config.settings import settings
from app.core.limiter import limiter
from app.db.models import (
    Acceso,
    ArchivoMultimedia,
    Dispositivo,
    Escaneado,
    EstadoCampus,
    EstadoEscaneoEnum,
    MediaProviderEnum,
    MediaStatusEnum,
    MediaTypeEnum,
    RoleEnum,
    SolicitudRegistroEstadoEnum,
    SolicitudRegistroVehiculo,
    TipoAccesoEnum,
    TipoVehiculo,
    UbicacionVehiculoEnum,
    Usuario,
    Vehiculo,
)
from app.db.session import get_db
from app.schemas.plate import EscaneadoResponse, PlateAnalysisResponse
from app.services.access_decision import infer_access_type, is_duplicate_access
from app.services.barrier_actuator import trigger_barrier_webhook
from app.services.cloudinary_storage import CloudinaryStorage
from app.services.image_processing import ImageProcessingError, ImageProcessingService
from app.services.media_tasks import process_media_record, spool_directory
from app.services.plate_analysis import analyze_plate_bytes, inspect_vehicle
from app.services.storage import StorageError
from app.services.vehicle_type import VehicleTypeResult
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png"]


@router.post("/analyze", response_model=PlateAnalysisResponse)
@limiter.limit("60/minute")
async def analyze_plate_endpoint(
    request: Request, 
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    realtime: bool = False,
    dispositivo_id: str | None = Form(None),
    placa_sugerida: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_scanner)
):
    request_started_at = perf_counter()
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400, 
            detail="Formato de archivo no permitido. Solo se aceptan imágenes JPEG y PNG."
        )
    
    image_bytes = await file.read(MAX_FILE_SIZE + 1)
    
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, 
            detail="El archivo es demasiado grande. El límite máximo es de 5MB."
        )
    
    plate_engine = getattr(request.app.state, "fast_alpr_engine", None)
    if plate_engine is None:
        raise HTTPException(
            status_code=503,
            detail="El motor OCR no está disponible en este momento."
        )

    result_dict, ocr_elapsed_ms = await analyze_plate_bytes(
        image_bytes,
        realtime,
        plate_engine,
    )
    logger.info(
        "Analisis de placa: etapa=ocr elapsed_ms=%.1f realtime=%s",
        ocr_elapsed_ms,
        realtime,
    )

    if result_dict.get("status") == "ERROR":
        return JSONResponse(
            status_code=int(result_dict.get("http_status", 422)),
            content=PlateAnalysisResponse(
                estado="ERROR",
                mensaje=result_dict.get("message", "Error desconocido durante el análisis."),
            ).model_dump(),
        )
    
    status_val = result_dict.get("status")
    vehicle = None
    acceso_id = None
    tipo_acceso_registrado = None
    solicitud_id = None
    color_result = None
    type_result = VehicleTypeResult(None, 0.0, "DESCONOCIDO")
    suggested_type_name = None

    # Una imagen estatica obtiene sugerencia aunque la placa ya este registrada,
    # el OCR requiera revision o no termine creando una solicitud. El modo
    # realtime evita ejecutar detector vehicular + CLIP en cada frame.
    if not realtime and result_dict.get("plate_bbox"):
        vehicle_detector = getattr(request.app.state, "vehicle_detector", None)
        clip_classifier = getattr(request.app.state, "clip_color_classifier", None)
        if vehicle_detector is not None:
            type_catalog = list((await db.execute(
                select(TipoVehiculo).where(TipoVehiculo.esta_activo.is_(True))
            )).scalars().all())
            inspection = await inspect_vehicle(
                image_bytes,
                result_dict.get("plate_bbox"),
                vehicle_detector,
                clip_classifier,
                type_catalog,
            )
            color_result = inspection.color
            type_result = inspection.vehicle_type
            suggested_type_name = inspection.suggested_type_name
            logger.info(
                "Analisis de placa: etapa=vehiculo elapsed_ms=%.1f realtime=%s",
                inspection.elapsed_ms,
                realtime,
            )
    # El análisis anónimo devuelve solo el resultado OCR. Consultas de vehículos,
    # escaneos, accesos y evidencias requieren una identidad autenticada.
    if status_val in ["DETECTED", "LOW_CONFIDENCE"]:
        normalized = result_dict.get("normalized_plate")
        
        vehicle = None
        if normalized:
            normalized = normalized.replace("-", "").replace(" ", "").upper().strip()
            v_res = await db.execute(
                select(Vehiculo)
                .options(selectinload(Vehiculo.propietario))
                .where(Vehiculo.placa == normalized)
            )
            vehicle = v_res.scalars().first()

        estado_enum = EstadoEscaneoEnum.DETECTADO if status_val == "DETECTED" else EstadoEscaneoEnum.BAJA_CONFIANZA

        disp_uuid = None
        dispositivo = None
        if dispositivo_id:
            try:
                disp_uuid = uuid.UUID(dispositivo_id)
                disp_res = await db.execute(select(Dispositivo).where(Dispositivo.id == disp_uuid))
                dispositivo = disp_res.scalars().first()
            except ValueError:
                pass

        # Si no hay dispositivo_id explícito pero el usuario autenticado es DISPOSITIVO,
        # resolver automáticamente por nombre (según convención del sistema)
        if current_user.rol == RoleEnum.DISPOSITIVO:
            dispositivo = None
            disp_uuid = None
            disp_res = await db.execute(
                select(Dispositivo).where(
                    Dispositivo.nombre == current_user.nombre,
                    Dispositivo.esta_activo == True
                )
            )
            dispositivo = disp_res.scalars().first()
            if dispositivo:
                disp_uuid = dispositivo.id

        scan = Escaneado(
            placa_detectada=result_dict.get("detected_plate"),
            placa_normalizada=normalized,
            confianza=result_dict.get("combined_confidence") or result_dict.get("ocr_confidence") or 0.0,
            estado=estado_enum,
            vehiculo_id=vehicle.id if vehicle else None,
            dispositivo_id=disp_uuid
        )
        db.add(scan)
        
        if vehicle:
            # Check if there is a recent access for this vehicle to prevent duplicates (cooldown)
            # TOCTOU-001: FOR UPDATE sobre Acceso para serializar el cooldown.
            # Solo lockea filas de Acceso (OF Acceso), no Escaneado.
            # Si dos requests llegan simultáneamente, el segundo espera el lock
            # hasta que el primero haga commit. La ventana de lock es breve:
            # solo el SELECT + check de cooldown, antes del I/O de imágenes.
            last_acceso_query = (
                select(Acceso)
                .join(Escaneado)
                .where(Escaneado.vehiculo_id == vehicle.id)
                .order_by(Acceso.creado_el.desc())
                .limit(1)
                .with_for_update(of=Acceso)
            )
            last_acceso_res = await db.execute(last_acceso_query)
            last_acceso = last_acceso_res.scalar_one_or_none()

            now_utc = datetime.now(timezone.utc)
            is_duplicate = is_duplicate_access(
                last_acceso.creado_el if last_acceso else None,
                now_utc,
                settings.CAMERA_DUPLICATE_COOLDOWN_SECONDS,
            )
            if is_duplicate:
                logger.info("Acceso duplicado para vehiculo %s omitido en el backend (cooldown)", vehicle.placa)

            if not is_duplicate:
                # 1. Determinar el tipo de acceso (ENTRADA o SALIDA)
                estado_campus = None
                tipo_acceso = None
                if dispositivo:
                    name_lower = dispositivo.nombre.lower()
                    if any(
                        token in name_lower
                        for token in ("entrada", "ingreso", "salida", "egreso")
                    ):
                        tipo_acceso = TipoAccesoEnum(infer_access_type(name_lower, None))
                
                if tipo_acceso is None:
                    # Consultar el último estado en el campus del vehículo
                    estado_res = await db.execute(select(EstadoCampus).where(EstadoCampus.vehiculo_id == vehicle.id))
                    estado_campus = estado_res.scalars().first()
                    tipo_acceso = TipoAccesoEnum(
                        infer_access_type(
                            None,
                            estado_campus.estado if estado_campus else None,
                        )
                    )

                # 2. Registrar el acceso
                ubicacion_acceso = dispositivo.ubicacion if dispositivo else "Portería Principal"
                log = Acceso(
                    tipo_acceso=tipo_acceso,
                    ubicacion=ubicacion_acceso,
                    escaneado=scan,
                    operador_usuario_id=None
                )
                db.add(log)

                # 3. Guardar imagen de evidencia
                media_type = (
                    MediaTypeEnum.ACCESS_ENTRY
                    if tipo_acceso == TipoAccesoEnum.ENTRADA
                    else MediaTypeEnum.ACCESS_EXIT
                )
                
                # Generar el UUID manualmente para evitar la necesidad de flush
                media_uuid = uuid.uuid4()
                media = ArchivoMultimedia(
                    id=media_uuid,
                    proveedor=MediaProviderEnum.CLOUDINARY,
                    tipo=media_type,
                    estado=MediaStatusEnum.PENDING,
                    resource_type="image",
                    delivery_type=settings.CLOUDINARY_DELIVERY_TYPE,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=settings.MEDIA_ACCESS_RETENTION_DAYS),
                )
                db.add(media)

                # Spool local de la imagen usando el UUID generado
                spool_path = spool_directory() / f"{media_uuid}.upload"
                await asyncio.to_thread(spool_path.write_bytes, image_bytes)
                media.spool_path = str(spool_path)
                log.imagen = media

                # 4. Actualizar EstadoCampus
                estado_res = await db.execute(select(EstadoCampus).where(EstadoCampus.vehiculo_id == vehicle.id))
                estado_campus = estado_res.scalars().first()
                nuevo_estado = UbicacionVehiculoEnum.DENTRO if tipo_acceso == TipoAccesoEnum.ENTRADA else UbicacionVehiculoEnum.FUERA
                if estado_campus:
                    estado_campus.estado = nuevo_estado
                    estado_campus.ultimo_acceso = log
                else:
                    estado_campus = EstadoCampus(
                        vehiculo_id=vehicle.id,
                        estado=nuevo_estado,
                        ultimo_acceso=log
                    )
                    db.add(estado_campus)

                # 5. Encolar tarea de subida a Cloudinary
                background_tasks.add_task(process_media_record, media_uuid)

                # Registrar para la respuesta
                await db.flush()
                acceso_id = log.id
                tipo_acceso_registrado = tipo_acceso.value

                # 6. Disparar webhook de barrera si el dispositivo tiene URL configurada
                if dispositivo and dispositivo.webhook_url:
                    background_tasks.add_task(
                        trigger_barrier_webhook,
                        dispositivo.webhook_url,
                        tipo_acceso.value
                    )
 
        try:
            await db.flush()
            # El polling nunca persiste evidencias ni crea solicitudes.
            target_plate = None
            if placa_sugerida:
                target_plate = placa_sugerida.replace("-", "").replace(" ", "").upper().strip()
            elif normalized:
                target_plate = normalized

            is_valid_format = False
            if target_plate:
                is_valid_format = validate_bolivian_plate(target_plate)

            if not realtime and target_plate and is_valid_format and vehicle is None:
                pending = await db.scalar(select(SolicitudRegistroVehiculo).where(
                    SolicitudRegistroVehiculo.placa_sugerida == target_plate,
                    SolicitudRegistroVehiculo.estado == SolicitudRegistroEstadoEnum.PENDING,
                ))
                processed = await run_in_threadpool(ImageProcessingService().process, image_bytes, MediaTypeEnum.VEHICLE_REGISTRATION.value)
                uploaded = await run_in_threadpool(CloudinaryStorage().upload, processed.content, MediaTypeEnum.VEHICLE_REGISTRATION.value)
                media = ArchivoMultimedia(proveedor=MediaProviderEnum.CLOUDINARY, tipo=MediaTypeEnum.VEHICLE_REGISTRATION, estado=MediaStatusEnum.READY, asset_id=uploaded.asset_id, public_id=uploaded.public_id, resource_type=uploaded.resource_type, delivery_type=uploaded.delivery_type, formato=uploaded.format, ancho=uploaded.width, alto=uploaded.height, peso_bytes=uploaded.bytes, intentos=1)
                db.add(media); await db.flush()
                
                if pending:
                    pending.escaneado_id = scan.id
                    pending.imagen_id = media.id
                    pending.confianza_placa = scan.confianza or 0.0
                    pending.color_sugerido = color_result.color_sugerido if color_result else "DESCONOCIDO"
                    pending.color_hex = color_result.color_hex if color_result else None
                    pending.confianza_color = color_result.confianza_color if color_result else 0.0
                    pending.metodo_color = color_result.metodo_color if color_result else "DESCONOCIDO"
                    pending.tipo_sugerido_id = type_result.tipo_sugerido_id
                    pending.confianza_tipo = type_result.confianza_tipo
                    pending.metodo_tipo = type_result.metodo_tipo
                    pending.creado_el = datetime.now(timezone.utc)
                    pending.creado_por_usuario_id = current_user.id
                    solicitud_id = pending.id
                else:
                    solicitud = SolicitudRegistroVehiculo(
                        escaneado_id=scan.id,
                        imagen_id=media.id,
                        placa_sugerida=target_plate,
                        confianza_placa=scan.confianza or 0.0,
                        color_sugerido=color_result.color_sugerido if color_result else "DESCONOCIDO",
                        color_hex=color_result.color_hex if color_result else None,
                        confianza_color=color_result.confianza_color if color_result else 0.0,
                        metodo_color=color_result.metodo_color if color_result else "DESCONOCIDO",
                        tipo_sugerido_id=type_result.tipo_sugerido_id,
                        confianza_tipo=type_result.confianza_tipo,
                        metodo_tipo=type_result.metodo_tipo,
                        estado=SolicitudRegistroEstadoEnum.PENDING,
                        creado_por_usuario_id=current_user.id,
                    )
                    db.add(solicitud); await db.flush(); solicitud_id = solicitud.id
            await db.commit()
        except (ImageProcessingError, StorageError, SQLAlchemyError):
            await db.rollback()
            raise HTTPException(status_code=503, detail="No se pudo guardar la evidencia de la solicitud")
        except Exception:
            await db.rollback()
            logger.exception("Error inesperado al persistir escaneo/solicitud")
            return JSONResponse(
                status_code=500,
                content=PlateAnalysisResponse(
                    estado="ERROR",
                    mensaje="Error interno al guardar el registro del escaneo.",
                ).model_dump(),
            )

    # Mapeo de la respuesta
    response = PlateAnalysisResponse(
        estado="DETECTADO" if result_dict.get("status") == "DETECTED" else ("BAJA_CONFIANZA" if result_dict.get("status") == "LOW_CONFIDENCE" else result_dict.get("status")),
        placa_detectada=result_dict.get("detected_plate") or placa_sugerida,
        placa_normalizada=result_dict.get("normalized_plate") or target_plate,
        es_formato_valido=result_dict.get("is_valid_bolivian_format", False) or is_valid_format,
        confianza=result_dict.get("combined_confidence"),
        ruta_imagen=result_dict.get("annotated_image") or result_dict.get("plate_crop"),
        plate_bbox=result_dict.get("plate_bbox"),
        raw_bboxes=result_dict.get("raw_bboxes"),
        solicitud_id=solicitud_id,
        vehiculo_id=vehicle.id if vehicle else None,
        acceso_id=acceso_id,
        tipo_acceso=tipo_acceso_registrado,
        es_registrado=vehicle is not None,
        # SEC-011: Solo exponer datos del propietario a usuarios autenticados
        propietario_nombre=(
            f"{vehicle.propietario.nombre} {vehicle.propietario.apellido_paterno}".strip()
            if (vehicle and vehicle.propietario) else None
        ),
        color_sugerido=color_result.color_sugerido if color_result else (
            "DESCONOCIDO" if not realtime else None
        ),
        confianza_color=color_result.confianza_color if color_result else (
            0.0 if not realtime else None
        ),
        metodo_color=color_result.metodo_color if color_result else (
            "DESCONOCIDO" if not realtime else None
        ),
        tipo_sugerido_id=type_result.tipo_sugerido_id if not realtime else None,
        tipo_sugerido=suggested_type_name if not realtime else None,
        confianza_tipo=type_result.confianza_tipo if not realtime else None,
        metodo_tipo=type_result.metodo_tipo if not realtime else None,
        mensaje=("Vehiculo desconocido. Solicitud enviada a revision" if solicitud_id else result_dict.get("message"))
    )
    logger.info(
        "Analisis de placa: etapa=total elapsed_ms=%.1f realtime=%s estado=%s",
        (perf_counter() - request_started_at) * 1000,
        realtime,
        response.estado,
    )
    return response


@router.get("/scans", response_model=list[EscaneadoResponse])
async def list_plate_scans(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_staff),
):
    query = select(Escaneado).order_by(Escaneado.creado_el.desc()).offset(skip).limit(limit)
    # Por ahora todos ven todo o solo admins
    if current_user.rol != RoleEnum.ADMINISTRADOR:
        # En el futuro filtrar por dispositivos que el operador gestiona
        pass
    result = await db.execute(query)
    return [EscaneadoResponse.model_validate(x) for x in result.scalars().all()]


@router.get("/health")
async def health_check(request: Request):
    fast_alpr_available = getattr(request.app.state, "fast_alpr_engine", None) is not None
    ocr_available = fast_alpr_available
    active_engine = getattr(
        request.app.state,
        "ocr_engine_name",
        "fast_alpr" if fast_alpr_available else "unavailable",
    )
    pipeline = get_pipeline_status()
    ready = bool(ocr_available and pipeline["supervision_available"])
    return {
        "status": "ok" if ready else "degraded",
        "message": (
            "API de ALPR lista para inferencia."
            if ready
            else "API disponible, pero ningun motor OCR esta inicializado."
        ),
        "ocr_available": ocr_available,
        "active_ocr_engine": active_engine,
        "fast_alpr_available": fast_alpr_available,
        **pipeline,
    }
