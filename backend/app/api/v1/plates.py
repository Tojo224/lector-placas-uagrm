import uuid
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Depends, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.schemas.plate import PlateAnalysisResponse, EscaneadoResponse
from app.ai.pipeline import analyze_plate, get_pipeline_status, classify_vehicle_attributes
from app.core.limiter import limiter
from app.db.session import get_db
from app.db.models import (
    Usuario, Escaneado, RoleEnum, Vehiculo, EstadoEscaneoEnum,
    Acceso, ArchivoMultimedia, EstadoCampus, Dispositivo,
    TipoAccesoEnum, UbicacionVehiculoEnum, MediaProviderEnum,
    MediaTypeEnum, MediaStatusEnum, SolicitudRegistroEstadoEnum, SolicitudRegistroVehiculo,
    Marca, TipoVehiculo
)
from app.services.image_processing import ImageProcessingService, ImageProcessingError
from app.services.cloudinary_storage import CloudinaryStorage
from app.services.storage import StorageError
from app.api.v1.auth import get_current_user, get_current_user_optional
from app.services.media_tasks import process_media_record, spool_directory
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png"]


async def _trigger_barrier_webhook(url: str, direction: str) -> None:
    """Dispara el webhook del actuador de barrera en background.
    Nunca lanza excepcion: si la barrera esta offline, el flujo continua normal."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(url, json={"action": "open", "direction": direction})
    except Exception:
        pass  # Barrera offline no es error critico del sistema


@router.post("/analyze", response_model=PlateAnalysisResponse)
@limiter.limit("60/minute")
async def analyze_plate_endpoint(
    request: Request, 
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    realtime: bool = False,
    dispositivo_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user_optional)
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400, 
            detail="Formato de archivo no permitido. Solo se aceptan imágenes JPEG y PNG."
        )
    
    image_bytes = await file.read()
    
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, 
            detail="El archivo es demasiado grande. El límite máximo es de 5MB."
        )
    
    ocr_reader = getattr(request.app.state, "ocr_reader", None)
    if ocr_reader is None:
        raise HTTPException(
            status_code=503,
            detail="El motor OCR no está disponible en este momento."
        )

    result_dict = await run_in_threadpool(
        analyze_plate,
        image_bytes,
        ocr_reader,
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
        if dispositivo is None and current_user is not None and current_user.rol.value == "DISPOSITIVO":
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

            cooldown = timedelta(seconds=settings.CAMERA_DUPLICATE_COOLDOWN_SECONDS)
            now_utc = datetime.now(timezone.utc)
            is_duplicate = False
            if last_acceso:
                last_time = last_acceso.creado_el
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=timezone.utc)
                if now_utc - last_time < cooldown:
                    is_duplicate = True
                    logger.info("Acceso duplicado para vehiculo %s omitido en el backend (cooldown)", vehicle.placa)

            if not is_duplicate:
                # 1. Determinar el tipo de acceso (ENTRADA o SALIDA)
                tipo_acceso = None
                if dispositivo:
                    name_lower = dispositivo.nombre.lower()
                    if "entrada" in name_lower or "ingreso" in name_lower:
                        tipo_acceso = TipoAccesoEnum.ENTRADA
                    elif "salida" in name_lower or "egreso" in name_lower:
                        tipo_acceso = TipoAccesoEnum.SALIDA
                
                if tipo_acceso is None:
                    # Consultar el último estado en el campus del vehículo
                    estado_res = await db.execute(select(EstadoCampus).where(EstadoCampus.vehiculo_id == vehicle.id))
                    estado_campus = estado_res.scalars().first()
                    if estado_campus and estado_campus.estado == UbicacionVehiculoEnum.DENTRO:
                        tipo_acceso = TipoAccesoEnum.SALIDA
                    else:
                        tipo_acceso = TipoAccesoEnum.ENTRADA

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
                        _trigger_barrier_webhook,
                        dispositivo.webhook_url,
                        tipo_acceso.value
                    )
 
        brand_sug = None
        type_sug = None
        color_sug = None

        try:
            await db.flush()
            # El polling nunca persiste evidencias ni crea solicitudes.
            if (not realtime and status_val == "DETECTED" and normalized and
                    result_dict.get("is_valid_bolivian_format", False) and
                    vehicle is None and current_user is not None):
                pending = await db.scalar(select(SolicitudRegistroVehiculo).where(
                    SolicitudRegistroVehiculo.placa_sugerida == normalized,
                    SolicitudRegistroVehiculo.estado == SolicitudRegistroEstadoEnum.PENDING,
                ))
                
                # Clasificar marca, tipo y color de forma asíncrona local si Hugging Face está disponible
                classifier = getattr(request.app.state, "vehicle_classifier", None)
                if classifier is not None:
                    # Obtener marcas y tipos activos del catálogo
                    brands_res = await db.execute(select(Marca.nombre).where(Marca.esta_activo == True))
                    types_res = await db.execute(select(TipoVehiculo.nombre).where(TipoVehiculo.esta_activo == True))
                    brands = [row[0] for row in brands_res.all()]
                    types = [row[0] for row in types_res.all()]
                    
                    # Decodificar imagen para el clasificador
                    img_np = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
                    if img_np is not None:
                        # Ejecutar en threadpool para no bloquear el loop de asyncio
                        classification = await run_in_threadpool(
                            classify_vehicle_attributes,
                            img_np,
                            classifier,
                            brands,
                            types
                        )
                        brand_sug = classification.get("brand")
                        type_sug = classification.get("type")
                        color_sug = classification.get("color")

                if not pending:
                    processed = await run_in_threadpool(ImageProcessingService().process, image_bytes, MediaTypeEnum.VEHICLE_REGISTRATION.value)
                    uploaded = await run_in_threadpool(CloudinaryStorage().upload, processed.content, MediaTypeEnum.VEHICLE_REGISTRATION.value)
                    media = ArchivoMultimedia(proveedor=MediaProviderEnum.CLOUDINARY, tipo=MediaTypeEnum.VEHICLE_REGISTRATION, estado=MediaStatusEnum.READY, asset_id=uploaded.asset_id, public_id=uploaded.public_id, resource_type=uploaded.resource_type, delivery_type=uploaded.delivery_type, formato=uploaded.format, ancho=uploaded.width, alto=uploaded.height, peso_bytes=uploaded.bytes, intentos=1)
                    db.add(media); await db.flush()
                    solicitud = SolicitudRegistroVehiculo(
                        escaneado_id=scan.id,
                        imagen_id=media.id,
                        placa_sugerida=normalized,
                        confianza_placa=scan.confianza or 0.0,
                        estado=SolicitudRegistroEstadoEnum.PENDING,
                        creado_por_usuario_id=current_user.id,
                        marca_sugerida=brand_sug,
                        tipo_sugerido=type_sug,
                        color_sugerido=color_sug
                    )
                    db.add(solicitud); await db.flush(); solicitud_id = solicitud.id
                else:
                    solicitud_id = pending.id
                    brand_sug = pending.marca_sugerida
                    type_sug = pending.tipo_sugerido
                    color_sug = pending.color_sugerido
            await db.commit()
        except (ImageProcessingError, StorageError):
            await db.rollback()
            raise HTTPException(status_code=503, detail="No se pudo guardar la evidencia de la solicitud")
        except Exception as exc:
            await db.rollback()
            logger.error("Error inesperado al persistir escaneo/solicitud: %s", exc, exc_info=True)
            return JSONResponse(
                status_code=500,
                content=PlateAnalysisResponse(
                    estado="ERROR",
                    mensaje="Error interno al guardar el registro del escaneo.",
                ).model_dump(),
            )

    # Mapeo de la respuesta
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
        # SEC-011: Solo exponer datos del propietario a usuarios autenticados
        propietario_nombre=(
            f"{vehicle.propietario.nombre} {vehicle.propietario.apellido_paterno}".strip()
            if (vehicle and vehicle.propietario and current_user is not None) else None
        ),
        mensaje=("Vehiculo desconocido. Solicitud enviada a revision" if solicitud_id else result_dict.get("message")),
        marca_sugerida=brand_sug,
        tipo_sugerido=type_sug,
        color_sugerido=color_sug
    )


@router.get("/scans", response_model=list[EscaneadoResponse])
async def list_plate_scans(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
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
    ocr_available = getattr(request.app.state, "ocr_reader", None) is not None
    pipeline = get_pipeline_status()
    ready = bool(ocr_available and pipeline["supervision_available"])
    return {
        "status": "ok" if ready else "degraded",
        "message": (
            "API de ALPR lista para inferencia."
            if ready
            else "API disponible, pero el motor OCR no esta inicializado."
        ),
        "ocr_available": ocr_available,
        **pipeline,
    }
