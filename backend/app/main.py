"""Punto de entrada principal de la aplicacion FastAPI."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
MPLCONFIG_DIR = RUNTIME_DIR / "matplotlib"
UPLOADS_DIR = PROJECT_ROOT / "uploads"

for directory in (RUNTIME_DIR, MPLCONFIG_DIR, UPLOADS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

try:
    from fast_alpr import ALPR
except ImportError:  # pragma: no cover - depends on the installed environment
    ALPR = None

try:
    from open_image_models.detection.factory import create_detector
except ImportError:  # pragma: no cover
    create_detector = None

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import plates
from app.api.v1.access_logs import router as access_logs_router
from app.api.v1.auth import router as auth_router
from app.api.v1.barrier import router as barrier_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.devices import router as devices_router
from app.api.v1.edge_snapshot import router as edge_snapshot_router
from app.api.v1.edge_sync import router as edge_sync_router
from app.api.v1.media import router as media_router
from app.api.v1.registration_requests import router as registration_requests_router
from app.api.v1.vehicles import router as vehicles_router
from app.config.settings import settings
from app.db.session import database_target
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())



def run_db_migrations() -> None:
    """Ejecuta de forma programática las migraciones de Alembic al iniciar."""
    from alembic.config import Config
    from alembic import command
    try:
        logger.info("Iniciando ejecución automática de migraciones de Alembic...")
        alembic_cfg = Config(PROJECT_ROOT / "alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        command.upgrade(alembic_cfg, "head")
        logger.info("Migraciones de base de datos completadas exitosamente.")
    except Exception as e:
        logger.error(f"Error ejecutando migraciones automáticas: {e}")


async def bootstrap_production_database() -> None:
    """Crea el primer administrador y siembra marcas por defecto si la base de datos está vacía."""
    from sqlalchemy.future import select
    from app.db.models import Usuario, RoleEnum, Marca
    from app.core.security import hash_password
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        # 1. Crear Administrador Inicial si no hay usuarios en la base de datos
        try:
            result = await session.execute(select(Usuario))
            if not result.scalars().first():
                logger.info("No se encontraron usuarios en la base de datos. Creando administrador inicial...")
                bootstrap_carnet = os.getenv("BOOTSTRAP_ADMIN_CARNET", "1111111")
                bootstrap_password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "AdminPassword123")
                bootstrap_nombre = os.getenv("BOOTSTRAP_ADMIN_NOMBRE", "Administrador")
                bootstrap_apellido = os.getenv("BOOTSTRAP_ADMIN_APELLIDO", "Sistema")

                admin_user = Usuario(
                    nombre=bootstrap_nombre,
                    apellido_paterno=bootstrap_apellido,
                    carnet=bootstrap_carnet,
                    contrasena_hash=hash_password(bootstrap_password),
                    rol=RoleEnum.ADMINISTRADOR,
                    esta_activo=True
                )
                session.add(admin_user)
                logger.info(f"Administrador creado -> Carnet: {bootstrap_carnet}")
        except Exception as e:
            logger.error(f"Error al verificar/crear administrador inicial: {e}")

        # 2. Crear Catálogo Base de Marcas si la tabla marcas está vacía
        try:
            brands_result = await session.execute(select(Marca))
            if not brands_result.scalars().first():
                logger.info("Catálogo de marcas vacío. Sembrando catálogo inicial de producción...")
                default_brands = ["Toyota", "Nissan", "Suzuki", "Honda", "Ford", "Chevrolet", "Mitsubishi", "Hyundai", "Kia"]
                for brand_name in default_brands:
                    session.add(Marca(nombre=brand_name))
                logger.info("Catálogo de marcas sembrado con éxito.")
        except Exception as e:
            logger.error(f"Error al sembrar marcas: {e}")

        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error al confirmar el bootstrap en la base de datos: {e}")
            await session.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Inicializa FastALPR/FastPlateOCR una sola vez."""
    # Ejecutar migraciones y bootstrap
    await asyncio.to_thread(run_db_migrations)
    await bootstrap_production_database()

    target = database_target()
    logger.info(
        "Base configurada: provider=%s host=%s database=%s",
        target["provider"],
        target["host"],
        target["database"],
    )
    app.state.fast_alpr_engine = None
    app.state.vehicle_detector = None
    if ALPR is None:
        logger.error("FastALPR/FastPlateOCR no esta instalado.")
    else:
        try:
            providers = [settings.FAST_ALPR_EXECUTION_PROVIDER]
            app.state.fast_alpr_engine = ALPR(
                detector_model=settings.FAST_ALPR_DETECTOR_MODEL,
                detector_conf_thresh=settings.FAST_ALPR_DETECTOR_CONFIDENCE,
                detector_providers=providers,
                ocr_model=settings.FAST_PLATE_OCR_MODEL,
                ocr_device="cpu",
                ocr_providers=providers,
            )
            logger.info(
                "FastALPR listo: detector=%s ocr=%s provider=%s",
                settings.FAST_ALPR_DETECTOR_MODEL,
                settings.FAST_PLATE_OCR_MODEL,
                settings.FAST_ALPR_EXECUTION_PROVIDER,
            )
        except Exception:
            logger.exception("FastALPR/FastPlateOCR no pudo inicializarse")

    try:
        if create_detector is None:
            raise RuntimeError("open-image-models no esta instalado")
        app.state.vehicle_detector = create_detector(
            settings.VEHICLE_DETECTOR_MODEL,
            conf_thresh=settings.VEHICLE_DETECTOR_CONFIDENCE,
            providers=[settings.FAST_ALPR_EXECUTION_PROVIDER],
        )
        logger.info(
            "Color vehicular listo: RF-DETR + OpenCV local, detector=%s",
            settings.VEHICLE_DETECTOR_MODEL,
        )
    except Exception:
        logger.exception("Detector vehicular/color OpenCV no pudo inicializarse")

    app.state.ocr_engine_name = "fast_alpr" if app.state.fast_alpr_engine is not None else "unavailable"
    yield
    for state_name in ("fast_alpr_engine", "vehicle_detector", "ocr_engine_name"):
        if hasattr(app.state, state_name):
            delattr(app.state, state_name)


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "API para localizar y leer placas bolivianas localmente con "
        "FastALPR, FastPlateOCR y OpenCV."
    ),
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # SEC-006: Solo los headers mínimos necesarios
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(plates.router, prefix="/api/v1/plates", tags=["Placas"])
app.include_router(vehicles_router, prefix="/api/v1/vehicles", tags=["Vehicles"])
app.include_router(devices_router, prefix="/api/v1/devices", tags=["Devices"])
app.include_router(edge_snapshot_router, prefix="/api/v1/edge-snapshot", tags=["Edge Snapshot"])
app.include_router(edge_sync_router, prefix="/api/v1/edge-sync", tags=["Edge Sync"])
app.include_router(media_router, prefix="/api/v1/media", tags=["Media"])
app.include_router(registration_requests_router, prefix="/api/v1/vehicle-registration-requests", tags=["Vehicle Registration Requests"])
app.include_router(
    access_logs_router,
    prefix="/api/v1/access-logs",
    tags=["Access Logs"],
)
app.include_router(barrier_router, prefix="/api/v1/barrier", tags=["Barrier Simulator"])

# SEC-010: Cabeceras de seguridad HTTP en todas las respuestas
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse
from starlette.responses import Response as StarletteResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.cookies.get("session_token")
        ):
            if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                return StarletteJSONResponse(
                    {"detail": "Solicitud de navegador no valida."},
                    status_code=403,
                )
            origin = request.headers.get("Origin")
            if origin and origin not in settings.ALLOWED_ORIGINS:
                return StarletteJSONResponse(
                    {"detail": "Origen no autorizado."},
                    status_code=403,
                )
        response: StarletteResponse = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permitir camara para el dispositivo movil en red local
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        if request.url.path.startswith(("/api/auth", "/api/v1/media")):
            response.headers["Cache-Control"] = "no-store"
        if request.url.scheme == "https" and not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Reload trigger comment to refresh FastAPI cache with new AuthRoleEnum
