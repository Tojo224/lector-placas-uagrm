from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import replace
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from app.services.image_processing import ImageProcessingError
from app.services.plate_analysis import analyze_plate_bytes
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.staticfiles import NotModifiedResponse
from starlette.types import Scope
from pydantic import BaseModel

from edge_agent import __version__
from edge_agent.cache import apply_snapshot
from edge_agent.config import EdgeSettings
from edge_agent.credentials import (
    DeviceCredentialProvider,
    default_device_credential_provider,
)
from edge_agent.db import EdgeDatabase
from edge_agent.db.repositories import ScanRepository
from edge_agent.engine import create_ocr_engine
from edge_agent.media_spool import MediaSpool, MediaSpoolError
from edge_agent.local_auth import LocalAuthError, LocalAuthService
from edge_agent.offline_access import OfflineAccessService
from edge_agent.product_config import ProductConfigStore, validate_central_url
from edge_agent.sync import SyncWorker

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
EDGE_STATIC_MIME_TYPES = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
}


def _edge_media_type(path: str | os.PathLike[str]) -> str | None:
    return EDGE_STATIC_MIME_TYPES.get(Path(path).suffix.lower())


class EdgeStaticFiles(StaticFiles):
    """Serve Vite assets without consulting host Windows MIME associations."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        request_headers = Headers(scope=scope)
        response = FileResponse(
            full_path,
            status_code=status_code,
            stat_result=stat_result,
            media_type=_edge_media_type(full_path),
        )
        if self.is_not_modified(response.headers, request_headers):
            return NotModifiedResponse(response.headers)
        return response


class SnapshotVehicle(BaseModel):
    central_id: str
    plate: str
    is_active: bool = True
    owner_name: str | None = None
    brand_name: str | None = None
    vehicle_type_name: str | None = None
    color: str | None = None
    source_updated_at: str | None = None


class SnapshotDevice(BaseModel):
    central_id: str
    name: str
    location: str
    direction: str = "AUTO"
    is_active: bool = True
    source_updated_at: str | None = None


class OperationalSnapshot(BaseModel):
    version: str
    generated_at: str
    vehicles: list[SnapshotVehicle]
    devices: list[SnapshotDevice]


class ProvisionRequest(BaseModel):
    central_url: str


class LocalLoginRequest(BaseModel):
    carnet: str
    contrasena: str


def _bearer_token(authorization: str | None) -> str | None:
    prefix = "Bearer "
    if authorization and authorization.startswith(prefix):
        return authorization[len(prefix):].strip() or None
    return None


def _ocr_response(result: dict[str, Any], outcome: dict[str, Any] | None = None) -> dict[str, Any]:
    status = result.get("status")
    outcome = outcome or {}
    return {
        "estado": (
            "DETECTADO"
            if status == "DETECTED"
            else "BAJA_CONFIANZA" if status == "LOW_CONFIDENCE" else status
        ),
        "placa_detectada": result.get("detected_plate"),
        "placa_normalizada": result.get("normalized_plate"),
        "es_formato_valido": result.get("is_valid_bolivian_format", False),
        "confianza": result.get("combined_confidence"),
        "ruta_imagen": result.get("annotated_image") or result.get("plate_crop"),
        "mensaje": result.get("message"),
        "plate_bbox": result.get("plate_bbox"),
        "raw_bboxes": result.get("raw_bboxes"),
        "solicitud_id": None,
        "vehiculo_id": outcome.get("vehicle_central_id"),
        "acceso_id": outcome.get("access_event_id"),
        "tipo_acceso": outcome.get("direction"),
        "es_registrado": outcome.get("vehicle_found", False),
        "propietario_nombre": outcome.get("vehicle_owner_name"),
        "color_sugerido": None,
        "confianza_color": None,
        "metodo_color": None,
        "tipo_sugerido_id": None,
        "tipo_sugerido": None,
        "confianza_tipo": None,
        "metodo_tipo": None,
        "vehiculo_encontrado": outcome.get("vehicle_found", False),
        "decision": outcome.get("decision"),
        "motivo": outcome.get("reason"),
        "estado_offline": outcome.get("offline_state"),
        "media_id": outcome.get("media_id"),
        "media_estado": outcome.get("media_status"),
    }


def create_edge_app(
    settings: EdgeSettings | None = None,
    engine_factory: Callable[[EdgeSettings], Any] = create_ocr_engine,
    credential_provider: DeviceCredentialProvider | None = None,
) -> FastAPI:
    edge_settings = settings or EdgeSettings.from_env()
    data_dir = edge_settings.resolved_data_dir()
    product_config_store = ProductConfigStore(data_dir)
    product_credential_provider = credential_provider or default_device_credential_provider(
        data_dir
    )

    async def replace_sync_worker(app: FastAPI, configured: EdgeSettings) -> None:
        if app.state.sync_worker:
            app.state.sync_worker.stop()
            if app.state.sync_task:
                await app.state.sync_task
        app.state.sync_worker = None
        app.state.sync_task = None
        if configured.sync_configured() and app.state.database is not None:
            app.state.sync_worker = SyncWorker(app.state.database, configured)
            app.state.sync_task = asyncio.create_task(app.state.sync_worker.run())

    async def provision_technical_identity(
        app: FastAPI, central_url: str, human_token: str
    ) -> None:
        stored = product_config_store.load()
        installation_id = product_config_store.ensure_installation_id(central_url)
        existing_secret = product_credential_provider.get_device_key()
        if stored.installation_provisioned and existing_secret:
            configured = replace(
                edge_settings,
                central_url=central_url,
                installation_id=installation_id,
                installation_key=existing_secret,
            )
            if app.state.sync_worker is None:
                await replace_sync_worker(app, configured)
            return
        try:
            async with httpx.AsyncClient(base_url=central_url, timeout=15.0) as client:
                response = await client.post(
                    "/api/v1/edge-sync/installations/provision",
                    json={"installation_id": installation_id},
                    headers={"Authorization": f"Bearer {human_token}"},
                )
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("installation_id")) != installation_id:
                raise ValueError("Identidad de instalación central inválida.")
            credential = str(payload.get("credential") or "").strip()
            if not credential:
                raise ValueError("Credencial técnica central vacía.")
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise LocalAuthError(
                "El usuario fue validado, pero no se pudo aprovisionar esta instalación.",
                503,
            ) from exc
        await asyncio.to_thread(product_credential_provider.store_device_key, credential)
        await asyncio.to_thread(
            product_config_store.save,
            central_url,
            None,
            installation_id,
            True,
        )
        configured = replace(
            edge_settings,
            central_url=central_url,
            installation_id=installation_id,
            installation_key=credential,
        )
        await replace_sync_worker(app, configured)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.lifecycle_state = "STARTING"
        app.state.started_at = datetime.now(timezone.utc)
        lifespan_started = perf_counter()
        app.state.startup_timings = {}
        app.state.analysis_count = 0
        app.state.ignored_frame_count = 0
        app.state.duplicate_frame_count = 0
        app.state.last_analysis_at = None
        app.state.database = None
        app.state.scan_repository = None
        app.state.database_error = None
        app.state.ocr_error = None
        app.state.ocr_engine = None
        app.state.sync_worker = None
        app.state.sync_task = None
        app.state.ocr_task = None
        app.state.local_auth = None
        try:
            database = EdgeDatabase(
                edge_settings.database_path(),
                edge_settings.sqlite_busy_timeout_ms,
            )
            await asyncio.to_thread(database.initialize)
            app.state.startup_timings["sqlite_initialize_ms"] = round(
                (perf_counter() - lifespan_started) * 1000, 1
            )
            app.state.database = database
            app.state.local_auth = LocalAuthService(
                database,
                on_online_validated=lambda central_url, token: provision_technical_identity(
                    app, central_url, token
                ),
            )
            app.state.scan_repository = ScanRepository(database)
            app.state.offline_access = OfflineAccessService(
                database, edge_settings.cache_max_age_hours,
                edge_settings.duplicate_cooldown_seconds,
            )
            app.state.media_spool = MediaSpool(database, edge_settings)
            app.state.analysis_count = await asyncio.to_thread(
                app.state.scan_repository.count
            )
            logger.info("SQLite edge inicializado")
            if edge_settings.sync_configured():
                app.state.sync_worker = SyncWorker(database, edge_settings)
                app.state.sync_task = asyncio.create_task(app.state.sync_worker.run())
        except Exception as exc:
            app.state.database_error = type(exc).__name__
            logger.exception("SQLite edge no pudo inicializarse")
        async def initialize_ocr() -> None:
            app.state.lifecycle_state = "INITIALIZING_OCR"
            try:
                app.state.ocr_engine = await asyncio.to_thread(
                    engine_factory, edge_settings
                )
                app.state.startup_timings.update(
                    getattr(app.state.ocr_engine, "_edge_startup_timings", {})
                )
                app.state.startup_timings["lifespan_to_ready_ms"] = round(
                    (perf_counter() - lifespan_started) * 1000, 1
                )
                app.state.lifecycle_state = "READY"
                logger.info("Edge OCR inicializado en modo local")
            except Exception as exc:
                app.state.ocr_error = type(exc).__name__
                app.state.lifecycle_state = "DEGRADED"
                logger.exception("El motor OCR local no pudo inicializarse")

        if edge_settings.initialize_ocr_in_background:
            app.state.ocr_task = asyncio.create_task(initialize_ocr())
        else:
            await initialize_ocr()
        yield
        if app.state.sync_worker:
            app.state.sync_worker.stop()
        if app.state.sync_task:
            await app.state.sync_task
        if app.state.ocr_task:
            await app.state.ocr_task
        app.state.ocr_engine = None
        app.state.scan_repository = None
        app.state.database = None

    app = FastAPI(
        title="UAGRM Plate Edge Agent",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.edge_settings = edge_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(edge_settings.ui_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        allow_private_network=True,
    )

    @app.middleware("http")
    async def private_network_and_cache_headers(request, call_next):
        response = await call_next(request)
        if request.headers.get("Access-Control-Request-Private-Network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        if request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.url.path == "/" or not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.post("/api/v1/edge/analyze")
    async def analyze(file: UploadFile = File(...), realtime: bool = False,
                      confirm: bool = True, device_id: str | None = Form(None)):
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Formato de archivo no permitido. Solo se aceptan imagenes JPEG y PNG.",
            )
        image_bytes = await file.read(MAX_FILE_SIZE + 1)
        if len(image_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="El archivo excede 5MB.")
        engine = app.state.ocr_engine
        if engine is None:
            raise HTTPException(status_code=503, detail="El motor OCR local no esta listo.")
        scan_repository = app.state.scan_repository
        if scan_repository is None:
            raise HTTPException(status_code=503, detail="SQLite local no esta listo.")

        started_at = perf_counter()
        result, ocr_elapsed_ms = await analyze_plate_bytes(
            image_bytes,
            realtime,
            engine,
            edge_settings.pipeline_config(),
        )
        if confirm:
            outcome = await asyncio.to_thread(
                app.state.offline_access.process, result, realtime, device_id
            )
        else:
            outcome = {"decision": "OCR_ONLY", "reason": "Lectura sin confirmar.",
                       "offline_state": "LOCAL_OCR", "vehicle_found": False,
                       "persisted": False}
        try:
            media_id = await asyncio.to_thread(
                app.state.media_spool.capture, image_bytes, outcome
            )
            outcome["media_id"] = media_id
            outcome["media_status"] = "PENDING" if media_id else None
        except (ImageProcessingError, MediaSpoolError, OSError) as exc:
            outcome["media_status"] = "FAILED_LOCAL"
            logger.warning("No se pudo conservar evidencia local: %s", type(exc).__name__)
        if outcome["decision"] == "NO_RELEVANT_OCR":
            app.state.ignored_frame_count += 1
        elif outcome["decision"] == "DUPLICATE":
            app.state.duplicate_frame_count += 1
        app.state.analysis_count = await asyncio.to_thread(scan_repository.count)
        app.state.last_analysis_at = datetime.now(timezone.utc)
        logger.info(
            "Edge OCR: elapsed_ms=%.1f total_ms=%.1f realtime=%s status=%s",
            ocr_elapsed_ms,
            (perf_counter() - started_at) * 1000,
            realtime,
            result.get("status"),
        )
        if result.get("status") == "ERROR":
            return JSONResponse(
                status_code=int(result.get("http_status", 422)),
                content=_ocr_response(result, outcome),
            )
        return _ocr_response(result, outcome)

    @app.post("/api/v1/edge/cache/snapshot")
    async def install_snapshot(snapshot: OperationalSnapshot):
        if app.state.database is None:
            raise HTTPException(status_code=503, detail="SQLite local no esta listo.")
        try:
            payload = snapshot.model_dump()
            return await asyncio.to_thread(apply_snapshot, app.state.database, payload)
        except Exception as exc:
            logger.exception("No se pudo aplicar el snapshot operativo")
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/edge/provision")
    async def provision(request: ProvisionRequest):
        try:
            central_url = validate_central_url(request.central_url)
            await asyncio.to_thread(
                product_config_store.ensure_installation_id, central_url
            )
            stored = product_config_store.load()
            device_key = product_credential_provider.get_device_key()
            configured = replace(
                edge_settings,
                central_url=central_url,
                installation_id=stored.installation_id,
                installation_key=(
                    device_key if stored.installation_provisioned else None
                ),
                device_id=edge_settings.device_id or stored.device_id,
                device_key=edge_settings.device_key or device_key,
            )
            await replace_sync_worker(app, configured)
            return {
                "status": "CONFIGURED",
                "central_url": central_url,
                "technical_credentials_preserved": bool(
                    (configured.installation_id and configured.installation_key)
                    or (configured.device_id and configured.device_key)
                ),
            }
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/edge/auth/login")
    async def local_login(request: LocalLoginRequest):
        if app.state.local_auth is None:
            raise HTTPException(status_code=503, detail="Autenticación local no disponible.")
        central_url = product_config_store.load().central_url or edge_settings.central_url
        try:
            result = await app.state.local_auth.login(
                central_url, request.carnet, request.contrasena
            )
            return {"token": result.token, "user": result.user, "mode": result.mode}
        except LocalAuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/v1/edge/auth/session")
    async def local_session(authorization: str | None = Header(default=None)):
        user = (
            app.state.local_auth.session(_bearer_token(authorization))
            if app.state.local_auth else None
        )
        if not user:
            raise HTTPException(status_code=401, detail="Sesión local inválida.")
        return {"user": user}

    @app.post("/api/v1/edge/auth/logout")
    async def local_logout(authorization: str | None = Header(default=None)):
        if app.state.local_auth:
            app.state.local_auth.logout(_bearer_token(authorization))
        return {"status": "SIGNED_OUT"}

    @app.get("/api/v1/edge/health")
    async def health():
        ocr_ready = app.state.ocr_engine is not None
        database_ready = app.state.database is not None
        ready = ocr_ready and database_ready
        cache = (app.state.offline_access.cache_status() if database_ready else
                 {"valid": False, "state": "UNAVAILABLE", "age_hours": None})
        sync = (app.state.sync_worker.status() if app.state.sync_worker else
                {"network": "offline", "configured": False, "last_sync_success_at": None,
                 "next_sync_attempt_at": None, "sync_error": None,
                 "pending": 0, "retry": 0, "dead_letters": 0, "synced": 0})
        media = (app.state.media_spool.stats() if database_ready else
                 {"spool_bytes": 0, "disk_free_bytes": None, "low_space": True})
        return {
            "status": "ok" if ready else "degraded",
            "lifecycle_state": app.state.lifecycle_state,
            "ready": ready,
            "ocr_ready": ocr_ready,
            "database_ready": database_ready,
            "access_ready": ready and cache["valid"],
            "cache": cache,
            "sync": sync,
            "media": media,
            "active_ocr_engine": "fast_alpr" if ocr_ready else "unavailable",
            "supervision_available": False,
            "camera_capture_supported": True,
            "pipeline_mode": "FAST_ALPR_FAST_PLATE_OCR",
            "startup_timings": app.state.startup_timings,
        }

    @app.get("/api/v1/edge/status")
    async def status():
        ocr_ready = app.state.ocr_engine is not None
        database_ready = app.state.database is not None
        ready = ocr_ready and database_ready
        cache = (app.state.offline_access.cache_status() if database_ready else
                 {"valid": False, "state": "UNAVAILABLE", "age_hours": None})
        sync = (app.state.sync_worker.status() if app.state.sync_worker else
                {"network": "offline", "configured": False, "last_sync_success_at": None,
                 "next_sync_attempt_at": None, "sync_error": None,
                 "pending": 0, "retry": 0, "dead_letters": 0, "synced": 0})
        media = (app.state.media_spool.stats() if database_ready else
                 {"spool_bytes": 0, "disk_free_bytes": None, "low_space": True})
        return {
            "status": "running",
            "lifecycle_state": app.state.lifecycle_state,
            "provisioned": edge_settings.sync_configured() or bool(
                product_config_store.load().central_url
                and product_credential_provider.get_device_key()
                and (
                    product_config_store.load().installation_provisioned
                    or product_config_store.load().device_id
                )
            ),
            "ready": ready,
            "ocr_ready": ocr_ready,
            "ocr_error": app.state.ocr_error,
            "database_ready": database_ready,
            "database_error": app.state.database_error,
            "database_path": str(edge_settings.database_path()),
            "started_at": app.state.started_at.isoformat(),
            "analysis_count": app.state.analysis_count,
            "ignored_frame_count": app.state.ignored_frame_count,
            "duplicate_frame_count": app.state.duplicate_frame_count,
            "cache": cache,
            "sync": sync,
            "media": media,
            "last_analysis_at": (
                app.state.last_analysis_at.isoformat()
                if app.state.last_analysis_at
                else None
            ),
            "network_mode": sync["network"],
            "bind_host": edge_settings.host,
            "startup_timings": app.state.startup_timings,
        }

    @app.get("/api/v1/edge/version")
    async def version():
        return {"name": "UAGRM Plate Edge Agent", "version": __version__}

    frontend_dir = edge_settings.resolved_frontend_dir()
    index_file = frontend_dir / "index.html"
    assets_dir = frontend_dir / "assets"
    if index_file.is_file():
        if assets_dir.is_dir():
            app.mount(
                "/assets",
                EdgeStaticFiles(directory=assets_dir),
                name="edge-ui-assets",
            )

        @app.get("/", include_in_schema=False)
        @app.get("/{frontend_path:path}", include_in_schema=False)
        async def edge_frontend(frontend_path: str = ""):
            if frontend_path == "assets" or frontend_path.startswith(("api/", "assets/")):
                raise HTTPException(status_code=404, detail="Ruta no encontrada.")
            candidate = (frontend_dir / frontend_path).resolve()
            if frontend_dir in candidate.parents and candidate.is_file():
                return FileResponse(candidate, media_type=_edge_media_type(candidate))
            return FileResponse(index_file, media_type="text/html")

    return app
