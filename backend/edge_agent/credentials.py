from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Protocol


class DeviceCredentialProvider(Protocol):
    def get_device_key(self) -> str | None: ...

    def store_device_key(self, value: str) -> None: ...


class EnvironmentDeviceCredentialProvider:
    """Development-only bridge. Productive installs use Windows DPAPI."""

    def get_device_key(self) -> str | None:
        return os.getenv("EDGE_DEVICE_KEY", "").strip() or None

    def store_device_key(self, value: str) -> None:
        raise RuntimeError("El proveedor de entorno no persiste credenciales.")


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


class WindowsDpapiCredentialProvider:
    """DPAPI CurrentUser store backed by one opaque binary file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _require_windows() -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows DPAPI solo esta disponible en Windows.")

    def store_device_key(self, value: str) -> None:
        self._require_windows()
        clear = value.strip().encode("utf-8")
        if not clear:
            raise ValueError("La credencial Edge esta vacia.")
        source, keepalive = _blob(clear)
        encrypted = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptProtectData(
            ctypes.byref(source), "UAGRM Plate Agent", None, None, None, 0,
            ctypes.byref(encrypted),
        ):
            raise ctypes.WinError()
        try:
            payload = ctypes.string_at(encrypted.pbData, encrypted.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(encrypted.pbData)
            del keepalive
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(self.path)

    def get_device_key(self) -> str | None:
        self._require_windows()
        if not self.path.is_file():
            return None
        source, keepalive = _blob(self.path.read_bytes())
        clear = _DataBlob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(clear)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(clear.pbData, clear.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(clear.pbData)
            del keepalive


def default_device_credential_provider(data_dir: Path) -> DeviceCredentialProvider:
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return WindowsDpapiCredentialProvider(data_dir / "config" / "device-key.dpapi")
    return EnvironmentDeviceCredentialProvider()
