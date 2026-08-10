from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.ai.ocr_types import OCRPipelineConfig
from edge_agent.credentials import (
    DeviceCredentialProvider,
    default_device_credential_provider,
)
from edge_agent.product_config import ProductConfigStore
from edge_agent.runtime import resource_path


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def default_data_dir() -> Path:
    configured = os.getenv("EDGE_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    program_data = os.getenv("PROGRAMDATA", "").strip()
    if program_data:
        return (Path(program_data) / "UAGRM" / "PlateAgent").resolve()
    local_data = os.getenv("LOCALAPPDATA", "").strip()
    if local_data:
        return (Path(local_data) / "UAGRM" / "PlateAgent").resolve()
    return (Path.home() / ".uagrm" / "plate-agent").resolve()


@dataclass(frozen=True)
class EdgeSettings:
    host: str = "127.0.0.1"
    port: int = 8765
    detector_model: str = "yolo-v9-t-384-license-plate-end2end"
    ocr_model: str = "cct-xs-v2-global-model"
    detector_confidence: float = 0.40
    execution_provider: str = "CPUExecutionProvider"
    ocr_confidence_threshold: float = 0.55
    roi_x: int | None = None
    roi_y: int | None = None
    roi_width: int | None = None
    roi_height: int | None = None
    data_dir: Path | None = None
    sqlite_busy_timeout_ms: int = 5000
    cache_max_age_hours: float = 24.0
    duplicate_cooldown_seconds: int = 30
    central_url: str | None = None
    device_id: str | None = None
    device_key: str | None = None
    snapshot_refresh_seconds: int = 900
    sync_poll_seconds: float = 5.0
    sync_timeout_seconds: float = 10.0
    sync_batch_size: int = 25
    sync_max_attempts: int = 10
    media_max_upload_bytes: int = 5 * 1024 * 1024
    media_min_free_bytes: int = 100 * 1024 * 1024
    frontend_dir: Path | None = None
    initialize_ocr_in_background: bool = False
    ui_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "https://127.0.0.1:5173",
        "http://localhost:5173",
        "https://localhost:5173",
    )

    @classmethod
    def from_env(
        cls, credential_provider: DeviceCredentialProvider | None = None
    ) -> EdgeSettings:
        host = os.getenv("EDGE_HOST", "127.0.0.1").strip()
        if host != "127.0.0.1":
            raise ValueError("EDGE_HOST debe ser 127.0.0.1 en esta fase.")
        data_dir = default_data_dir()
        product_config = ProductConfigStore(data_dir).load()
        provider = credential_provider or default_device_credential_provider(data_dir)
        return cls(
            host=host,
            port=int(os.getenv("EDGE_PORT", "8765")),
            detector_model=os.getenv(
                "EDGE_FAST_ALPR_DETECTOR_MODEL",
                "yolo-v9-t-384-license-plate-end2end",
            ),
            ocr_model=os.getenv(
                "EDGE_FAST_PLATE_OCR_MODEL", "cct-xs-v2-global-model"
            ),
            detector_confidence=float(
                os.getenv("EDGE_FAST_ALPR_DETECTOR_CONFIDENCE", "0.40")
            ),
            execution_provider=os.getenv(
                "EDGE_FAST_ALPR_EXECUTION_PROVIDER", "CPUExecutionProvider"
            ),
            ocr_confidence_threshold=float(
                os.getenv("EDGE_OCR_CONFIDENCE_THRESHOLD", "0.55")
            ),
            roi_x=_optional_int("EDGE_OCR_ROI_X"),
            roi_y=_optional_int("EDGE_OCR_ROI_Y"),
            roi_width=_optional_int("EDGE_OCR_ROI_WIDTH"),
            roi_height=_optional_int("EDGE_OCR_ROI_HEIGHT"),
            data_dir=data_dir,
            sqlite_busy_timeout_ms=int(
                os.getenv("EDGE_SQLITE_BUSY_TIMEOUT_MS", "5000")
            ),
            cache_max_age_hours=float(os.getenv("EDGE_CACHE_MAX_AGE_HOURS", "24")),
            duplicate_cooldown_seconds=int(
                os.getenv("EDGE_DUPLICATE_COOLDOWN_SECONDS", "30")
            ),
            central_url=(os.getenv("EDGE_CENTRAL_URL", "").strip()
                         or product_config.central_url),
            device_id=(os.getenv("EDGE_DEVICE_ID", "").strip()
                       or product_config.device_id),
            device_key=provider.get_device_key(),
            snapshot_refresh_seconds=int(os.getenv("EDGE_SNAPSHOT_REFRESH_SECONDS", "900")),
            sync_poll_seconds=float(os.getenv("EDGE_SYNC_POLL_SECONDS", "5")),
            sync_timeout_seconds=float(os.getenv("EDGE_SYNC_TIMEOUT_SECONDS", "10")),
            sync_batch_size=int(os.getenv("EDGE_SYNC_BATCH_SIZE", "25")),
            sync_max_attempts=int(os.getenv("EDGE_SYNC_MAX_ATTEMPTS", "10")),
            media_max_upload_bytes=int(
                os.getenv("EDGE_MEDIA_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))
            ),
            media_min_free_bytes=int(
                os.getenv("EDGE_MEDIA_MIN_FREE_BYTES", str(100 * 1024 * 1024))
            ),
            frontend_dir=(Path(os.environ["EDGE_FRONTEND_DIR"]).expanduser().resolve()
                          if os.getenv("EDGE_FRONTEND_DIR", "").strip() else None),
            ui_origins=tuple(
                origin.strip() for origin in os.getenv(
                    "EDGE_UI_ORIGINS",
                    "http://127.0.0.1:5173,https://127.0.0.1:5173,"
                    "http://localhost:5173,https://localhost:5173",
                ).split(",") if origin.strip()
            ),
            initialize_ocr_in_background=os.getenv(
                "EDGE_BACKGROUND_OCR_INIT", "1"
            ).strip().lower() not in {"0", "false", "no"},
        )

    def sync_configured(self) -> bool:
        return bool(self.central_url and self.device_id and self.device_key)

    def resolved_data_dir(self) -> Path:
        return (self.data_dir or default_data_dir()).expanduser().resolve()

    def database_path(self) -> Path:
        return self.resolved_data_dir() / "data" / "edge-agent.sqlite3"

    def media_spool_dir(self) -> Path:
        return self.resolved_data_dir() / "spool"

    def resolved_frontend_dir(self) -> Path:
        if self.frontend_dir:
            return self.frontend_dir.expanduser().resolve()
        return resource_path("frontend", "dist")

    def pipeline_config(self) -> OCRPipelineConfig:
        return OCRPipelineConfig(
            confidence_threshold=self.ocr_confidence_threshold,
            roi_x=self.roi_x,
            roi_y=self.roi_y,
            roi_width=self.roi_width,
            roi_height=self.roi_height,
            use_supervision_annotations=False,
        )
