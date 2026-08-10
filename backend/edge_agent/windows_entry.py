from __future__ import annotations

import ctypes
import logging
import sys
from contextlib import AbstractContextManager
from types import TracebackType

from edge_agent.config import EdgeSettings
from edge_agent.runtime import (
    configure_offline_model_runtime,
    configure_production_logging,
)


class WindowsSingleInstance(AbstractContextManager["WindowsSingleInstance"]):
    ERROR_ALREADY_EXISTS = 183

    def __init__(self, name: str = "Local\\UAGRMPlateAgent") -> None:
        self.name = name
        self.handle: int | None = None

    def __enter__(self) -> "WindowsSingleInstance":
        if sys.platform != "win32":
            return self
        kernel32 = ctypes.windll.kernel32
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise OSError("No se pudo crear el mutex de instancia unica.")
        if kernel32.GetLastError() == self.ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(self.handle)
            self.handle = None
            raise RuntimeError("UAGRM Plate Agent ya se esta ejecutando.")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.handle and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


def main() -> int:
    configure_offline_model_runtime()
    settings = EdgeSettings.from_env()
    log_file = configure_production_logging(settings.resolved_data_dir())
    logger = logging.getLogger(__name__)
    try:
        with WindowsSingleInstance():
            from edge_agent.app import create_edge_app
            import uvicorn

            logger.info(
                "Iniciando UAGRM Plate Agent en http://%s:%s; logs=%s",
                settings.host,
                settings.port,
                log_file,
            )
            uvicorn.run(
                create_edge_app(settings),
                host=settings.host,
                port=settings.port,
                reload=False,
                log_config=None,
            )
    except RuntimeError as exc:
        logger.error("No se inicio una segunda instancia: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
