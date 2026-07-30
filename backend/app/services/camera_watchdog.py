from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


class CameraWatchdog:
    def __init__(self, check_interval: float = 15.0) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._start_count: int = 0
        self._check_interval = check_interval
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _spawn(self) -> subprocess.Popen[str]:
        self._start_count += 1
        logger.info("Spawning camera capture (attempt %d)...", self._start_count)
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.services.camera_capture"],
            cwd=str(BACKEND_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        logger.info("Camera capture started (PID=%d, attempt=%d)", proc.pid, self._start_count)
        return proc

    def start(self) -> None:
        if self.is_alive:
            logger.warning("Camera watchdog: process already running")
            return
        self._process = self._spawn()
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="camera-watchdog"
        )
        self._monitor_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._kill_process()
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None

    def _kill_process(self) -> None:
        proc = self._process
        if proc is None:
            return
        if proc.poll() is None:
            logger.info("Terminating camera capture (PID=%d)...", proc.pid)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Camera capture did not terminate, killing (PID=%d)...", proc.pid)
                proc.kill()
                proc.wait()
        self._process = None

    def restart(self) -> None:
        logger.info("Restarting camera capture...")
        self._kill_process()
        self._process = self._spawn()

    def ensure_alive(self) -> bool:
        if self._process is None:
            self.start()
        elif not self.is_alive:
            logger.warning("Camera process died (was PID=%d), restarting...", self._process.pid)
            self.restart()
        return self.is_alive

    def health(self) -> dict:
        proc = self._process
        alive = self.is_alive
        return {
            "alive": alive,
            "pid": proc.pid if alive and proc is not None else None,
            "start_count": self._start_count,
            "monitor_active": self._monitor_thread is not None and self._monitor_thread.is_alive(),
        }

    def _monitor_loop(self) -> None:
        logger.info("Camera watchdog monitor started (interval=%.1fs)", self._check_interval)
        while not self._stop_event.wait(self._check_interval):
            try:
                if not self.is_alive:
                    old_pid = self._process.pid if self._process is not None else None
                    logger.warning("Camera monitor: process died (was PID=%s), restarting...", old_pid)
                    self.restart()
            except Exception:
                logger.exception("Camera watchdog monitor error")
        logger.info("Camera watchdog monitor stopped")
