import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.ai.pipeline import analyze_plate, get_pipeline_status
from app.api.v1.auth import require_scanner, require_scanner_or_api_token, require_staff
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
from app.services.cloudinary_storage import CloudinaryStorage
from app.services.image_processing import ImageProcessingError, ImageProcessingService
from app.services.media_tasks import process_media_record, spool_directory
from app.services.storage import StorageError
from app.services.vehicle_color import HybridVehicleColorAnalyzer
from app.services.vehicle_detection import VehicleAssociationService
from app.services.vehicle_type import VehicleTypeResult, VehicleTypeSuggester
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


async def _trigger_barrier_webhook(url: str, direction: str) -> None:
    """Dispara el webhook del actuador de barrera en background.
    Nunca lanza excepcion: si la barrera esta offline, el flujo continua normal."""
    from urllib.parse import urlsplit

    import httpx

    parsed = urlsplit(url)
    if (
        parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.path.rstrip("/") == "/api/v1/barrier/trigger"
    ):
        from app.api.v1.barrier import enqueue_barrier_event

        await enqueue_barrier_event(direction=direction)
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                url,
                json={"action": "open", "direction": direction},
                follow_redirects=False,
            )
            response.raise_for_status()
    except httpx.HTTPError:
        pass  # Barrera offline no es error critico del sistema


async def _validate_upload(file: UploadFile) -> bytes:
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
    return image_bytes


async def _enrich_with_detection(
    result_dict: dict,
    image_bytes: bytes,
    request: Request,
    db: AsyncSession,
) -> dict | None:
    if not result_dict.get("plate_bbox"):
        return None
    vehicle_detector = getattr(request.app.state, "vehicle_detector", None)
    clip_classifier = getattr(request.app.state, "clip_color_classifier", None)
    association = None
    type_result = VehicleTypeResult(None, 0.0, "DESCONOCIDO")
    suggested_type_name = None
    color_result = None
    if vehicle_detector is not None:
        association = await asyncio.wait_for(
            run_in_threadpool(
                VehicleAssociationService(vehicle_detector).detect_bytes,
                image_bytes,
                result_dict.get("plate_bbox"),
            ),
            timeout=settings.OCR_INFERENCE_TIMEOUT_SECONDS,
        )
        type_catalog = list((await db.execute(
            select(TipoVehiculo).where(TipoVehiculo.esta_activo.is_(True))
        )).scalars().all())
        type_result = VehicleTypeSuggester.resolve(association, type_catalog)
        if type_result.tipo_sugerido_id is not None:
            suggested_type_name = next(
                (item.nombre for item in type_catalog if item.id == type_result.tipo_sugerido_id),
                None,
            )
    if association is not None and clip_classifier is not None:
        color_result = await asyncio.wait_for(
            run_in_threadpool(
                HybridVehicleColorAnalyzer(vehicle_detector, clip_classifier).analyze,
                image_bytes,
                result_dict.get("plate_bbox"),
                association,
            ),
            timeout=settings.OCR_INFERENCE_TIMEOUT_SECONDS,
        )
    return {
        "type_result": type_result,
        "suggested_type_name": suggested_type_name,
        "color_result": color_result,
    }


async def _handle_cooldown(vehicle_id: int, db: AsyncSession) -> bool:
    last_acceso_query = (
        select(Acceso)
        .join(Escaneado)
        .where(Escaneado.vehiculo_id == vehicle_id)
        .order_by(Acceso.creado_el.desc())
        .limit(1)
        .with_for_update(of=Acceso)
    )
    last_acceso_res = await db.execute(last_acceso_query)
    last_acceso = last_acceso_res.scalar_one_or_none()
    if not last_acceso:
        return False
    cooldown = timedelta(seconds=settings.CAMERA_DUPLICATE_COOLDOWN_SECONDS)
    now_utc = datetime.now(timezone.utc)
    last_time = last_acceso.creado_el
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=timezone.utc)
    return now_utc - last_time < cooldown


async def _register_access(
    vehicle: Vehiculo,
    scan: Escaneado,
    dispositivo: Dispositivo | None,
    image_bytes: bytes,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> Acceso:
    tipo_acceso = None
    if dispositivo:
        name_lower = dispositivo.nombre.lower()
        if "entrada" in name_lower or "ingreso" in name_lower:
            tipo_acceso = TipoAccesoEnum.ENTRADA
        elif "salida" in name_lower or "egreso" in name_lower:
            tipo_acceso = TipoAccesoEnum.SALIDA
    estado_res = await db.execute(select(EstadoCampus).where(EstadoCampus.vehiculo_id == vehicle.id))
    estado_campus = estado_res.scalars().first()
    if tipo_acceso is None:
        if estado_campus and estado_campus.estado == UbicacionVehiculoEnum.DENTRO:
            tipo_acceso = TipoAccesoEnum.SALIDA
        else:
            tipo_acceso = TipoAccesoEnum.ENTRADA
    ubicacion_acceso = dispositivo.ubicacion if dispositivo else "Portería Principal"
    log = Acceso(
        tipo_acceso=tipo_acceso,
        ubicacion=ubicacion_acceso,
        escaneado=scan,
        operador_usuario_id=None,
    )
    db.add(log)
    media_type = (
        MediaTypeEnum.ACCESS_ENTRY
        if tipo_acceso == TipoAccesoEnum.ENTRADA
        else MediaTypeEnum.ACCESS_EXIT
    )
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
    spool_path = spool_directory() / f"{media_uuid}.upload"
    await asyncio.to_thread(spool_path.write_bytes, image_bytes)
    media.spool_path = str(spool_path)
    log.imagen = media
    nuevo_estado = UbicacionVehiculoEnum.DENTRO if tipo_acceso == TipoAccesoEnum.ENTRADA else UbicacionVehiculoEnum.FUERA
    if estado_campus:
        estado_campus.estado = nuevo_estado
        estado_campus.ultimo_acceso = log
    else:
        estado_campus = EstadoCampus(
            vehiculo_id=vehicle.id,
            estado=nuevo_estado,
            ultimo_acceso=log,
        )
        db.add(estado_campus)
    background_tasks.add_task(process_media_record, media_uuid)
    await db.flush()
    if dispositivo and dispositivo.webhook_url:
        background_tasks.add_task(
            _trigger_barrier_webhook,
            dispositivo.webhook_url,
            tipo_acceso.value,
        )
    return log


def _color_result_field(color_result, field: str, default=None):
    if color_result is None:
        return default
    return getattr(color_result, field, default)


def _type_result_field(type_result: VehicleTypeResult, field: str, realtime: bool):
    if realtime:
        return None
    return getattr(type_result, field, None)


def _build_plate_response(
    result_dict: dict,
    vehicle: Vehiculo | None,
    acceso_id: int | None,
    tipo_acceso_registrado: str | None,
    solicitud_id: int | None,
    color_result,
    type_result: VehicleTypeResult,
    suggested_type_name: str | None,
    realtime: bool,
) -> PlateAnalysisResponse:
    return PlateAnalysisResponse(
        estado="DETECTADO" if result_dict.get("status") == "DETECTED" else ("BAJA_CONFIANZA" if result_dict.get("status") == "LOW_CONFIDENCE" else result_dict.get("status")),
        placa_detectada=result_dict.get("detected_plate"),
        placa_normalizada=result_dict.get("normalized_plate"),
        es_formato_valido=result_dict.get("is_valid_bolivian_format", False),
        confianza=result_dict.get("combined_confidence"),
        ruta_imagen=result_dict.get("annotated_image") or result_dict.get("plate_crop"),
        plate_bbox=result_dict.get("plate_bbox"),
        raw_bboxes=result_dict.get("raw_bboxes"),
        solicitud_id=solicitud_id,
        vehiculo_id=vehicle.id if vehicle else None,
        acceso_id=acceso_id,
        tipo_acceso=tipo_acceso_registrado,
        es_registrado=vehicle is not None,
        propietario_nombre=(
            f"{vehicle.propietario.nombre} {vehicle.propietario.apellido_paterno}".strip()
            if (vehicle and vehicle.propietario) else None
        ),
        color_sugerido=_color_result_field(
            color_result, "color_sugerido", None if realtime else "DESCONOCIDO"
        ),
        confianza_color=_color_result_field(
            color_result, "confianza_color", None if realtime else 0.0
        ),
        metodo_color=_color_result_field(
            color_result, "metodo_color", None if realtime else "DESCONOCIDO"
        ),
        tipo_sugerido_id=_type_result_field(type_result, "tipo_sugerido_id", realtime),
        tipo_sugerido=None if realtime else suggested_type_name,
        confianza_tipo=_type_result_field(type_result, "confianza_tipo", realtime),
        metodo_tipo=_type_result_field(type_result, "metodo_tipo", realtime),
        ocr_unavailable=result_dict.get("ocr_unavailable", False),
        fallback_attempted=result_dict.get("fallback_attempted", False),
        mensaje=("Vehiculo desconocido. Solicitud enviada a revision" if solicitud_id else result_dict.get("message")),
    )


@router.post("/analyze", response_model=PlateAnalysisResponse)
@limiter.limit("60/minute")
async def analyze_plate_endpoint(
    request: Request, 
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    realtime: bool = False,
    dispositivo_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_scanner_or_api_token)
):
    image_bytes = await _validate_upload(file)

    plate_engine = getattr(request.app.state, "fast_alpr_engine", None)
    if plate_engine is None:
        raise HTTPException(
            status_code=503,
            detail="El motor OCR no está disponible en este momento."
        )

    try:
        result_dict = await asyncio.wait_for(
            run_in_threadpool(analyze_plate, image_bytes, realtime, plate_engine),
            timeout=settings.OCR_INFERENCE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"error": "ocr_timeout", "message": "OCR inference timed out"},
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

    if not realtime:
        detection = await _enrich_with_detection(result_dict, image_bytes, request, db)
        if detection:
            type_result = detection["type_result"]
            suggested_type_name = detection["suggested_type_name"]
            color_result = detection["color_result"]

    if status_val in ["DETECTED", "LOW_CONFIDENCE"]:
        normalized = result_dict.get("normalized_plate")

        if normalized:
            normalized = normalized.replace("-", "").replace(" ", "").upper().strip()
            v_res = await db.execute(select(Vehiculo).where(Vehiculo.placa == normalized))
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

        combined = result_dict.get("combined_confidence")
        ocr_conf = result_dict.get("ocr_confidence")
        confidence = combined if combined is not None else (ocr_conf if ocr_conf is not None else 0.0)
        scan = Escaneado(
            placa_detectada=result_dict.get("detected_plate"),
            placa_normalizada=normalized,
            confianza=confidence,
            estado=estado_enum,
            vehiculo_id=vehicle.id if vehicle else None,
            dispositivo_id=disp_uuid,
        )
        db.add(scan)

        if vehicle:
            await db.execute(
                select(Vehiculo).where(Vehiculo.id == vehicle.id).with_for_update()
            )

            if await _handle_cooldown(vehicle.id, db):
                logger.info("Acceso duplicado para vehiculo %s omitido en el backend (cooldown)", vehicle.placa)
            else:
                acceso = await _register_access(vehicle, scan, dispositivo, image_bytes, db, background_tasks)
                acceso_id = acceso.id
                tipo_acceso_registrado = acceso.tipo_acceso.value

        try:
            await db.flush()

            if (not realtime and status_val == "DETECTED" and normalized and
                    result_dict.get("is_valid_bolivian_format", False) and
                    vehicle is None):
                pending = await db.scalar(select(SolicitudRegistroVehiculo).where(
                    SolicitudRegistroVehiculo.placa_sugerida == normalized,
                    SolicitudRegistroVehiculo.estado == SolicitudRegistroEstadoEnum.PENDING,
                ))
                if not pending:
                    processed = await run_in_threadpool(ImageProcessingService().process, image_bytes, MediaTypeEnum.VEHICLE_REGISTRATION.value)
                    uploaded = await run_in_threadpool(CloudinaryStorage().upload, processed.content, MediaTypeEnum.VEHICLE_REGISTRATION.value)
                    media = ArchivoMultimedia(proveedor=MediaProviderEnum.CLOUDINARY, tipo=MediaTypeEnum.VEHICLE_REGISTRATION, estado=MediaStatusEnum.READY, asset_id=uploaded.asset_id, public_id=uploaded.public_id, resource_type=uploaded.resource_type, delivery_type=uploaded.delivery_type, formato=uploaded.format, ancho=uploaded.width, alto=uploaded.height, peso_bytes=uploaded.bytes, intentos=1)
                    db.add(media)
                    await db.flush()
                    solicitud = SolicitudRegistroVehiculo(
                        escaneado_id=scan.id,
                        imagen_id=media.id,
                        placa_sugerida=normalized,
                        confianza_placa=scan.confianza or 0.0,
                        color_sugerido=color_result.color_sugerido if color_result else "DESCONOCIDO",
                        confianza_color=color_result.confianza_color if color_result else 0.0,
                        metodo_color=color_result.metodo_color if color_result else "DESCONOCIDO",
                        tipo_sugerido_id=type_result.tipo_sugerido_id,
                        confianza_tipo=type_result.confianza_tipo,
                        metodo_tipo=type_result.metodo_tipo,
                        estado=SolicitudRegistroEstadoEnum.PENDING,
                        creado_por_usuario_id=current_user.id,
                    )
                    db.add(solicitud)
                    await db.flush()
                    solicitud_id = solicitud.id
                else:
                    solicitud_id = pending.id
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

    return _build_plate_response(
        result_dict=result_dict,
        vehicle=vehicle,
        acceso_id=acceso_id,
        tipo_acceso_registrado=tipo_acceso_registrado,
        solicitud_id=solicitud_id,
        color_result=color_result,
        type_result=type_result,
        suggested_type_name=suggested_type_name,
        realtime=realtime,
    )


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
