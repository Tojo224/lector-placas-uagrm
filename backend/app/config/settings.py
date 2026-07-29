from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Required environment variables (must be defined in .env)
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    ALLOWED_ORIGINS: list[str]
    DATABASE_URL: str
    CAMERA_API_URL: str = "http://127.0.0.1:8000/api/v1/plates/analyze"

    # App Settings
    APP_NAME: str = "Lector de Placas UAGRM"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Auth configuration
    SECRET_KEY: str = "change-this-in-env"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Local OCR pipeline configuration
    OCR_GPU: bool = False
    OCR_CONFIDENCE_THRESHOLD: float = 0.55
    OCR_UPSCALE_FACTOR: float = 2.0
    OCR_USE_GRAYSCALE: bool = True
    OCR_USE_CONTRAST: bool = True
    OCR_DENOISE: bool = True
    OCR_USE_THRESHOLD: bool = False
    OCR_ROI_X: int | None = None
    OCR_ROI_Y: int | None = None
    OCR_ROI_WIDTH: int | None = None
    OCR_ROI_HEIGHT: int | None = None

    # Hugging Face CLIP Zero-Shot settings
    HF_MODEL_NAME: str = "openai/clip-vit-base-patch32"
    ENABLE_HF_CLASSIFICATION: bool = True

    # Local camera agent configuration. The agent runs as a separate process.
    CAMERA_INDEX: int = 0
    CAMERA_RTSP_URL: str = ""
    CAMERA_ANALYSIS_INTERVAL_SECONDS: float = 2.0
    CAMERA_DUPLICATE_COOLDOWN_SECONDS: float = 30.0
    CAMERA_RECONNECT_DELAY_SECONDS: float = 5.0
    CAMERA_REQUEST_TIMEOUT_SECONDS: float = 30.0
    CAMERA_REQUEST_RETRIES: int = 2
    CAMERA_REQUEST_RETRY_DELAY_SECONDS: float = 1.0
    CAMERA_JPEG_QUALITY: int = 90

    # Provider-neutral media settings. Empty credentials keep local/unit tests usable.
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_SECURE: bool = True
    CLOUDINARY_ASSET_PREFIX: str = "placas-academico"
    CLOUDINARY_DELIVERY_TYPE: str = "authenticated"
    MEDIA_USER_SIZE: int = 512
    MEDIA_VEHICLE_MAX_DIMENSION: int = 1600
    MEDIA_ACCESS_MAX_DIMENSION: int = 1600
    MEDIA_PERMANENT_WEBP_QUALITY: int = 82
    MEDIA_ACCESS_WEBP_QUALITY: int = 78
    MEDIA_MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
    MEDIA_SIGNED_URL_TTL_SECONDS: int = 300
    MEDIA_ACCESS_RETENTION_DAYS: int = 90
    MEDIA_UPLOAD_MAX_RETRIES: int = 3
    MEDIA_SPOOL_DIR: str = ".runtime/media-spool"

    @field_validator(
        "DEBUG",
        "OCR_GPU",
        "OCR_USE_GRAYSCALE",
        "OCR_USE_CONTRAST",
        "OCR_DENOISE",
        "OCR_USE_THRESHOLD",
        "CLOUDINARY_SECURE",
        "ENABLE_HF_CLASSIFICATION",
        mode="before",
    )
    @classmethod
    def normalize_bool(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production"}:
                return False
        return bool(value)

    @field_validator("OCR_ROI_X", "OCR_ROI_Y", "OCR_ROI_WIDTH", "OCR_ROI_HEIGHT", mode="before")
    @classmethod
    def empty_roi_to_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        from sqlalchemy.engine import make_url

        url = make_url(value)
        if url.get_backend_name() != "postgresql":
            raise ValueError("DATABASE_URL debe apuntar a PostgreSQL")
        if url.drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL debe usar el driver postgresql+psycopg")
        if not url.host or not url.database:
            raise ValueError("DATABASE_URL debe incluir host y base de datos")
        if url.host.endswith(".neon.tech") and url.query.get("sslmode") not in {
            "require",
            "verify-ca",
            "verify-full",
        }:
            raise ValueError("Las conexiones a Neon requieren sslmode=require o superior")
        return value

    @field_validator("CLOUDINARY_DELIVERY_TYPE")
    @classmethod
    def authenticated_media_only(cls, value: str) -> str:
        if value != "authenticated":
            raise ValueError("CLOUDINARY_DELIVERY_TYPE debe ser authenticated")
        return value

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
