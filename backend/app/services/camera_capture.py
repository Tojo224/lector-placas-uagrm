from __future__ import annotations

import json
import logging
import signal
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import cv2
import numpy as np

from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraCaptureConfig:
    camera_index: int
    rtsp_url: str
    api_url: str
    analysis_interval_seconds: float
    duplicate_cooldown_seconds: float
    reconnect_delay_seconds: float
    request_timeout_seconds: float
    request_retries: int
    request_retry_delay_seconds: float
    jpeg_quality: int

    def __post_init__(self) -> None:
        if self.camera_index < 0:
            raise ValueError("CAMERA_INDEX no puede ser negativo.")
        if not self.api_url.strip():
            raise ValueError("CAMERA_API_URL es obligatorio.")
        if self.analysis_interval_seconds <= 0:
            raise ValueError("CAMERA_ANALYSIS_INTERVAL_SECONDS debe ser mayor que cero.")
        if self.duplicate_cooldown_seconds < 0:
            raise ValueError("CAMERA_DUPLICATE_COOLDOWN_SECONDS no puede ser negativo.")
        if self.reconnect_delay_seconds <= 0:
            raise ValueError("CAMERA_RECONNECT_DELAY_SECONDS debe ser mayor que cero.")
        if self.request_timeout_seconds <= 0:
            raise ValueError("CAMERA_REQUEST_TIMEOUT_SECONDS debe ser mayor que cero.")
        if self.request_retries < 0:
            raise ValueError("CAMERA_REQUEST_RETRIES no puede ser negativo.")
        if self.request_retry_delay_seconds < 0:
            raise ValueError("CAMERA_REQUEST_RETRY_DELAY_SECONDS no puede ser negativo.")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("CAMERA_JPEG_QUALITY debe estar entre 1 y 100.")

    @classmethod
    def from_settings(cls) -> CameraCaptureConfig:
        return cls(
            camera_index=settings.CAMERA_INDEX,
            rtsp_url=settings.CAMERA_RTSP_URL.strip(),
            api_url=settings.CAMERA_API_URL.strip(),
            analysis_interval_seconds=settings.CAMERA_ANALYSIS_INTERVAL_SECONDS,
            duplicate_cooldown_seconds=settings.CAMERA_DUPLICATE_COOLDOWN_SECONDS,
            reconnect_delay_seconds=settings.CAMERA_RECONNECT_DELAY_SECONDS,
            request_timeout_seconds=settings.CAMERA_REQUEST_TIMEOUT_SECONDS,
            request_retries=settings.CAMERA_REQUEST_RETRIES,
            request_retry_delay_seconds=settings.CAMERA_REQUEST_RETRY_DELAY_SECONDS,
            jpeg_quality=settings.CAMERA_JPEG_QUALITY,
        )

    @property
    def source(self) -> int | str:
        return self.rtsp_url if self.rtsp_url else self.camera_index

    @property
    def source_label(self) -> str:
        # Never include an RTSP URL because it may contain credentials.
        return "RTSP configurado" if self.rtsp_url else f"webcam indice {self.camera_index}"


class PlateDeduplicator:
    def __init__(
        self,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self._seen: dict[str, float] = {}

    def accept(self, plate: str) -> bool:
        normalized = plate.strip().upper()
        if not normalized:
            return False

        now = self.clock()
        cutoff = now - self.cooldown_seconds
        self._seen = {key: seen_at for key, seen_at in self._seen.items() if seen_at > cutoff}
        previous = self._seen.get(normalized)
        if previous is not None and now - previous < self.cooldown_seconds:
            return False

        self._seen[normalized] = now
        return True


def _build_multipart_request(api_url: str, jpeg_bytes: bytes) -> Request:
    parsed_url = urlsplit(api_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("CAMERA_API_URL debe usar http o https y contener un host valido.")
    boundary = f"----plate-camera-{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="camera-frame.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode("ascii") + jpeg_bytes + f"\r\n--{boundary}--\r\n".encode("ascii")
    headers: dict[str, str] = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    if settings.CAMERA_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CAMERA_API_TOKEN}"
    return Request(
        api_url,
        data=body,
        method="POST",
        headers=headers,
    )


def post_jpeg(api_url: str, jpeg_bytes: bytes, timeout_seconds: float) -> dict[str, Any]:
    request = _build_multipart_request(api_url, jpeg_bytes)
    try:
        # _build_multipart_request restringe el destino a HTTP(S) con host valido.
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            payload = response.read()
    except HTTPError as exc:
        payload = exc.read()
        if not payload:
            raise RuntimeError(f"El endpoint de analisis respondio HTTP {exc.code}.") from exc
    return json.loads(payload.decode("utf-8"))


class CameraCaptureAgent:
    def __init__(
        self,
        config: CameraCaptureConfig,
        capture_factory: Callable[[int | str], Any] = cv2.VideoCapture,
        sender: Callable[[str, bytes, float], dict[str, Any]] = post_jpeg,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.config = config
        self.capture_factory = capture_factory
        self.sender = sender
        self.stop_event = stop_event or threading.Event()
        self.deduplicator = PlateDeduplicator(config.duplicate_cooldown_seconds)
        self._capture: Any | None = None

    def stop(self) -> None:
        self.stop_event.set()
        capture = self._capture
        if capture is not None:
            capture.release()

    def _open_capture(self) -> Any | None:
        capture = self.capture_factory(self.config.source)
        if not capture.isOpened():
            capture.release()
            logger.warning("No se pudo abrir %s; se reintentara.", self.config.source_label)
            return None
        return capture

    def process_frame(self, frame: np.ndarray) -> bool:
        encoded, buffer = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality],
        )
        if not encoded:
            logger.warning("OpenCV no pudo codificar el fotograma como JPEG.")
            return False

        result = None
        for attempt in range(self.config.request_retries + 1):
            try:
                result = self.sender(
                    self.config.api_url,
                    buffer.tobytes(),
                    self.config.request_timeout_seconds,
                )
                break
            except (OSError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
                if attempt >= self.config.request_retries:
                    logger.warning(
                        "No se pudo analizar el fotograma tras %s intento(s): %s",
                        attempt + 1,
                        exc,
                    )
                    return False
                logger.warning(
                    "Fallo al enviar fotograma (intento %s/%s); se reintentara.",
                    attempt + 1,
                    self.config.request_retries + 1,
                )
                if self.stop_event.wait(self.config.request_retry_delay_seconds):
                    return False

        if result is None:
            return False

        status = str(result.get("status", "UNKNOWN"))
        plate = str(result.get("normalized_plate") or "").strip().upper()
        if status == "DETECTED" and plate:
            if not self.deduplicator.accept(plate):
                logger.info("Lectura duplicada omitida durante el cooldown: %s", plate)
                return False
            logger.info("Placa detectada por la camara: %s", plate)
            return True

        if result.get("requires_manual_review"):
            logger.info("La captura requiere revision manual; estado=%s.", status)
        else:
            logger.debug("Captura procesada sin placa confirmada; estado=%s.", status)
        return False

    def run(self) -> None:
        logger.info(
            "Agente de camara iniciado con %s; intervalo=%.2fs.",
            self.config.source_label,
            self.config.analysis_interval_seconds,
        )
        while not self.stop_event.is_set():
            capture = self._open_capture()
            if capture is None:
                self.stop_event.wait(self.config.reconnect_delay_seconds)
                continue

            self._capture = capture
            logger.info("Camara conectada: %s.", self.config.source_label)
            try:
                while not self.stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        logger.warning("Se perdio la camara; se intentara reconectar.")
                        break
                    self.process_frame(frame)
                    self.stop_event.wait(self.config.analysis_interval_seconds)
            except Exception:
                logger.exception("Fallo inesperado en el ciclo de captura.")
            finally:
                capture.release()
                self._capture = None

            if not self.stop_event.is_set():
                self.stop_event.wait(self.config.reconnect_delay_seconds)
        logger.info("Agente de camara detenido y recurso liberado.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    agent = CameraCaptureAgent(CameraCaptureConfig.from_settings())

    def request_stop(_signum: int, _frame: Any) -> None:
        agent.stop()

    for signal_name in ("SIGINT", "SIGTERM"):
        current_signal = getattr(signal, signal_name, None)
        if current_signal is not None:
            signal.signal(current_signal, request_stop)

    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    main()
