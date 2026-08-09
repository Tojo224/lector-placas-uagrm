from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000


class ImageProcessingError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    width: int
    height: int
    format: str
    bytes: int


@dataclass(frozen=True)
class ImageProcessingConfig:
    max_upload_bytes: int = 5 * 1024 * 1024
    user_size: int = 512
    vehicle_max_dimension: int = 1600
    access_max_dimension: int = 1600
    permanent_webp_quality: int = 82
    access_webp_quality: int = 78


class ImageProcessingService:
    def __init__(self, config: ImageProcessingConfig | None = None) -> None:
        if config is None:
            from app.config.settings import settings

            config = ImageProcessingConfig(
                max_upload_bytes=settings.MEDIA_MAX_UPLOAD_BYTES,
                user_size=settings.MEDIA_USER_SIZE,
                vehicle_max_dimension=settings.MEDIA_VEHICLE_MAX_DIMENSION,
                access_max_dimension=settings.MEDIA_ACCESS_MAX_DIMENSION,
                permanent_webp_quality=settings.MEDIA_PERMANENT_WEBP_QUALITY,
                access_webp_quality=settings.MEDIA_ACCESS_WEBP_QUALITY,
            )
        self.config = config

    def process(self, content: bytes, media_type: str) -> ProcessedImage:
        if not content:
            raise ImageProcessingError("La imagen esta vacia")
        if len(content) > self.config.max_upload_bytes:
            raise ImageProcessingError("La imagen excede el tamano permitido")

        try:
            with Image.open(io.BytesIO(content)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(content)) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
                if media_type == "USER_PROFILE":
                    image = self._user_image(image)
                    quality = self.config.permanent_webp_quality
                elif media_type == "VEHICLE_REGISTRATION":
                    image = self._limited(
                        image, self.config.vehicle_max_dimension
                    )
                    quality = self.config.permanent_webp_quality
                elif media_type in {"ACCESS_ENTRY", "ACCESS_EXIT"}:
                    image = self._limited(image, self.config.access_max_dimension)
                    quality = self.config.access_webp_quality
                else:
                    raise ImageProcessingError("Tipo multimedia no soportado")

                image = self._rgb(image)
                output = io.BytesIO()
                image.save(
                    output,
                    format="WEBP",
                    quality=quality,
                    method=6,
                    exif=b"",
                    icc_profile=None,
                )
                encoded = output.getvalue()
                return ProcessedImage(
                    content=encoded,
                    width=image.width,
                    height=image.height,
                    format="webp",
                    bytes=len(encoded),
                )
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise ImageProcessingError("La imagen esta corrupta o no es valida") from exc
        except Image.DecompressionBombError as exc:
            raise ImageProcessingError("La imagen excede las dimensiones seguras") from exc

    @staticmethod
    def _rgb(image: Image.Image) -> Image.Image:
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, "white")
            alpha = image.getchannel("A")
            background.paste(image.convert("RGB"), mask=alpha)
            return background
        return image.convert("RGB")

    @staticmethod
    def _limited(image: Image.Image, max_dimension: int) -> Image.Image:
        copy = image.copy()
        copy.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        return copy

    def _user_image(self, image: Image.Image) -> Image.Image:
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        cropped = image.crop((left, top, left + side, top + side))
        return cropped.resize(
            (self.config.user_size, self.config.user_size),
            Image.Resampling.LANCZOS,
        )
