from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from app.config.settings import BACKEND_DIR, settings
from app.db.models import ArchivoMultimedia, MediaStatusEnum
from app.db.session import AsyncSessionLocal
from app.services.cloudinary_storage import CloudinaryStorage
from app.services.image_processing import ImageProcessingError, ImageProcessingService
from app.services.storage import StorageError

logger = logging.getLogger(__name__)


def spool_directory() -> Path:
    path = Path(settings.MEDIA_SPOOL_DIR)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


async def process_media_record(media_id: UUID) -> None:
    """Owns its DB sessions; safe to call from BackgroundTasks or maintenance."""
    for _ in range(settings.MEDIA_UPLOAD_MAX_RETRIES):
        async with AsyncSessionLocal() as session:
            media = await session.get(ArchivoMultimedia, media_id)
            if not media or media.estado in {
                MediaStatusEnum.READY,
                MediaStatusEnum.DELETED,
            }:
                return
            media.estado = MediaStatusEnum.PROCESSING
            media.intentos += 1
            await session.commit()
            spool_path = Path(media.spool_path or "")
            media_type = media.tipo.value

        try:
            original = await asyncio.to_thread(spool_path.read_bytes)
            processed = await asyncio.to_thread(
                ImageProcessingService().process, original, media_type
            )
            uploaded = await asyncio.wait_for(
                asyncio.to_thread(
                    CloudinaryStorage().upload, processed.content, media_type
                ),
                timeout=settings.CLOUDINARY_UPLOAD_TIMEOUT_SECONDS,
            )
        except (OSError, StorageError, ImageProcessingError, ValueError, TypeError, asyncio.TimeoutError) as exc:
            async with AsyncSessionLocal() as session:
                media = await session.get(ArchivoMultimedia, media_id)
                if not media:
                    return
                media.estado = MediaStatusEnum.FAILED
                media.ultimo_error = (
                    "Cloudinary upload timed out"
                    if isinstance(exc, asyncio.TimeoutError)
                    else str(exc)
                    if isinstance(exc, (StorageError, ImageProcessingError))
                    else "No se pudo procesar o almacenar la evidencia"
                )[:500]
                await session.commit()
            logger.warning("Evidencia %s fallo en intento %s: %s", media_id, media.intentos, type(exc).__name__)
            continue

        async with AsyncSessionLocal() as session:
            media = await session.get(ArchivoMultimedia, media_id)
            if not media:
                return
            media.asset_id = uploaded.asset_id
            media.public_id = uploaded.public_id
            media.resource_type = uploaded.resource_type
            media.delivery_type = uploaded.delivery_type
            media.formato = uploaded.format
            media.ancho = uploaded.width
            media.alto = uploaded.height
            media.peso_bytes = uploaded.bytes
            media.estado = MediaStatusEnum.READY
            media.ultimo_error = None
            media.spool_path = None
            await session.commit()
        try:
            await asyncio.to_thread(spool_path.unlink, missing_ok=True)
        except OSError:
            logger.warning("No se pudo retirar un archivo temporal ya procesado")
        return
