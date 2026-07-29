"""Punto de entrada principal de la aplicacion FastAPI."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
OCR_MODEL_DIR = RUNTIME_DIR / "paddleocr"
MPLCONFIG_DIR = RUNTIME_DIR / "matplotlib"
UPLOADS_DIR = PROJECT_ROOT / "uploads"

for directory in (RUNTIME_DIR, OCR_MODEL_DIR, MPLCONFIG_DIR, UPLOADS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

try:
    from paddleocr import PaddleOCR
except ImportError:  # pragma: no cover - depends on the installed environment
    PaddleOCR = None

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import plates
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.vehicles import router as vehicles_router
from app.api.v1.access_logs import router as access_logs_router
from app.api.v1.devices import router as devices_router
from app.api.v1.media import router as media_router
from app.api.v1.barrier import router as barrier_router
from app.api.v1.registration_requests import router as registration_requests_router
from app.config.settings import settings
from app.db.session import database_target

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())



@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Inicializa PaddleOCR y Hugging Face CLIP una vez y libera referencias al apagar."""
    target = database_target()
    logger.info(
        "Base configurada: provider=%s host=%s database=%s",
        target["provider"],
        target["host"],
        target["database"],
    )
    if PaddleOCR is None:
        logger.warning("PaddleOCR no esta instalado; el pipeline OCR estara deshabilitado.")
        app.state.ocr_reader = None
    else:
        try:
            app.state.ocr_reader = PaddleOCR(
                lang="en",
                use_textline_orientation=True,
                device="gpu" if settings.OCR_GPU else "cpu",
                enable_mkldnn=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
        except Exception as exc:
            logger.warning("PaddleOCR no pudo inicializarse durante el arranque: %s", exc)
            app.state.ocr_reader = None

    # Inicializar Hugging Face Zero-Shot Classifier
    if settings.ENABLE_HF_CLASSIFICATION:
        try:
            from transformers import pipeline
            logger.info("Cargando modelo Zero-Shot CLIP de Hugging Face (%s)...", settings.HF_MODEL_NAME)
            app.state.vehicle_classifier = pipeline(
                "zero-shot-image-classification",
                model=settings.HF_MODEL_NAME,
                device=-1,  # CPU obligatoriamente
            )
        except Exception as exc:
            logger.warning("Hugging Face no pudo inicializarse durante el arranque: %s", exc)
            app.state.vehicle_classifier = None
    else:
        app.state.vehicle_classifier = None

    yield

    if hasattr(app.state, "ocr_reader"):
        del app.state.ocr_reader
    if hasattr(app.state, "vehicle_classifier"):
        del app.state.vehicle_classifier


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "API para localizar y leer placas bolivianas localmente con "
        "OpenCV, PaddleOCR y Supervision."
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
from starlette.responses import Response as StarletteResponse

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response: StarletteResponse = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permitir camara para el dispositivo movil en red local
        response.headers["Permissions-Policy"] = "camera=(*), microphone=(), geolocation=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Reload trigger comment to refresh FastAPI cache with new AuthRoleEnum
