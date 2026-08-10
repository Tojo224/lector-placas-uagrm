from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProductConfig:
    central_url: str | None = None
    installation_id: str | None = None
    installation_provisioned: bool = False
    device_id: str | None = None


class ProductConfigStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "config" / "agent.json"

    def load(self) -> ProductConfig:
        if not self.path.is_file():
            return ProductConfig()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return ProductConfig(
            central_url=str(payload.get("central_url") or "").strip() or None,
            installation_id=(
                str(payload.get("installation_id") or "").strip() or None
            ),
            installation_provisioned=bool(payload.get("installation_provisioned", False)),
            device_id=str(payload.get("device_id") or "").strip() or None,
        )

    def save(
        self,
        central_url: str,
        device_id: str | None = None,
        installation_id: str | None = None,
        installation_provisioned: bool | None = None,
    ) -> None:
        normalized = validate_central_url(central_url)
        current = self.load()
        preserved_device_id = device_id
        if preserved_device_id is None:
            preserved_device_id = current.device_id
        preserved_installation_id = installation_id or current.installation_id
        preserved_provisioned = (
            current.installation_provisioned
            if installation_provisioned is None else installation_provisioned
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({
                "schema_version": 2,
                "central_url": normalized,
                "installation_id": (
                    (preserved_installation_id or "").strip() or None
                ),
                "installation_provisioned": preserved_provisioned,
                "device_id": (preserved_device_id or "").strip() or None,
            }, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def ensure_installation_id(self, central_url: str) -> str:
        current = self.load()
        installation_id = current.installation_id or str(uuid.uuid4())
        self.save(central_url, installation_id=installation_id)
        return installation_id


def validate_central_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("La URL central no es valida.")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("La URL central productiva debe usar HTTPS.")
    return normalized
