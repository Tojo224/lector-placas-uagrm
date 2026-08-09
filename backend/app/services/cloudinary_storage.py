from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.settings import settings
from app.services.storage import (
    StorageConfigurationError,
    StorageError,
    StorageService,
    StorageUploadResult,
    TemporaryUrl,
)

logger = logging.getLogger(__name__)

FOLDERS = {
    "USER_PROFILE": "users",
    "VEHICLE_REGISTRATION": "vehicles",
    "ACCESS_ENTRY": "access/entries",
    "ACCESS_EXIT": "access/exits",
}


class CloudinaryStorage(StorageService):
    def __init__(self) -> None:
        missing = [
            name
            for name in (
                "CLOUDINARY_CLOUD_NAME",
                "CLOUDINARY_API_KEY",
                "CLOUDINARY_API_SECRET",
            )
            if not getattr(settings, name)
        ]
        if missing:
            raise StorageConfigurationError(
                "Falta configuracion de almacenamiento: " + ", ".join(missing)
            )

        import cloudinary

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=settings.CLOUDINARY_SECURE,
        )

    def upload(
        self, content: bytes, media_type: str, public_id: str | None = None
    ) -> StorageUploadResult:
        if media_type not in FOLDERS:
            raise StorageError("Tipo multimedia no soportado")
        try:
            import cloudinary.uploader
            from cloudinary.exceptions import Error as CloudinaryError

            result = cloudinary.uploader.upload(
                io.BytesIO(content),
                public_id=public_id or str(uuid4()),
                asset_folder=f"{settings.CLOUDINARY_ASSET_PREFIX}/{FOLDERS[media_type]}",
                resource_type="image",
                type=settings.CLOUDINARY_DELIVERY_TYPE,
                format="webp",
                overwrite=public_id is not None,
            )
            return StorageUploadResult(
                asset_id=result["asset_id"],
                public_id=result["public_id"],
                resource_type=result.get("resource_type", "image"),
                delivery_type=result.get("type", settings.CLOUDINARY_DELIVERY_TYPE),
                format=result["format"],
                width=int(result["width"]),
                height=int(result["height"]),
                bytes=int(result["bytes"]),
            )
        except StorageError:
            raise
        except (CloudinaryError, OSError) as exc:
            logger.warning("Fallo el proveedor de almacenamiento durante upload")
            raise StorageError("No se pudo almacenar la imagen") from exc

    def delete(self, public_id: str) -> bool:
        try:
            import cloudinary.uploader
            from cloudinary.exceptions import Error as CloudinaryError

            result = cloudinary.uploader.destroy(
                public_id,
                resource_type="image",
                type=settings.CLOUDINARY_DELIVERY_TYPE,
                invalidate=True,
            )
            return result.get("result") in {"ok", "not found"}
        except (CloudinaryError, OSError) as exc:
            logger.warning("Fallo el proveedor de almacenamiento durante delete")
            raise StorageError("No se pudo eliminar la imagen") from exc

    def replace(
        self, old_public_id: str | None, content: bytes, media_type: str
    ) -> StorageUploadResult:
        uploaded = self.upload(content, media_type)
        if old_public_id:
            try:
                self.delete(old_public_id)
            except StorageError:
                logger.warning("La imagen nueva se conservo; no se elimino la anterior")
        return uploaded

    def exists(self, public_id: str) -> bool:
        try:
            import cloudinary.api
            from cloudinary.exceptions import Error as CloudinaryError
            from cloudinary.exceptions import NotFound

            cloudinary.api.resource(
                public_id,
                resource_type="image",
                type=settings.CLOUDINARY_DELIVERY_TYPE,
            )
            return True
        except NotFound:
            return False
        except (CloudinaryError, OSError) as exc:
            if getattr(exc, "http_code", None) == 404:
                return False
            raise StorageError("No se pudo comprobar la imagen") from exc

    def get_temporary_url(self, public_id: str, fmt: str) -> TemporaryUrl:
        try:
            import cloudinary.utils
            from cloudinary.exceptions import Error as CloudinaryError

            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=settings.MEDIA_SIGNED_URL_TTL_SECONDS
            )
            url = cloudinary.utils.private_download_url(
                public_id,
                fmt,
                resource_type="image",
                type=settings.CLOUDINARY_DELIVERY_TYPE,
                expires_at=int(expires_at.timestamp()),
            )
            return TemporaryUrl(url=url, expires_at=expires_at)
        except (CloudinaryError, OSError) as exc:
            raise StorageError("No se pudo generar la URL temporal") from exc
