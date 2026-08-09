from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.image_processing import ImageProcessingConfig, ImageProcessingService

from edge_agent.config import EdgeSettings
from edge_agent.db import EdgeDatabase
from edge_agent.db.database import utc_now
from edge_agent.db.repositories import new_id


class MediaSpoolError(ValueError):
    pass


class MediaSpool:
    def __init__(self, database: EdgeDatabase, settings: EdgeSettings) -> None:
        self.database = database
        self.settings = settings
        self.root = settings.media_spool_dir().resolve()
        self.processor = ImageProcessingService(ImageProcessingConfig(
            max_upload_bytes=settings.media_max_upload_bytes,
        ))

    def capture(self, content: bytes, outcome: dict[str, Any]) -> str | None:
        access_event_id = outcome.get("access_event_id")
        scan_id = outcome.get("scan_id")
        direction = outcome.get("direction")
        if not access_event_id or not scan_id or direction not in {"ENTRADA", "SALIDA"}:
            return None
        media_type = "ACCESS_ENTRY" if direction == "ENTRADA" else "ACCESS_EXIT"
        processed = self.processor.process(content, media_type)
        self.root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(self.root)
        if usage.free - processed.bytes < self.settings.media_min_free_bytes:
            raise MediaSpoolError("Espacio insuficiente para conservar evidencia")

        media_id = new_id()
        now = datetime.now(timezone.utc)
        relative = Path("access") / f"{now:%Y}" / f"{now:%m}" / f"{media_id}.webp"
        final_path = (self.root / relative).resolve()
        if self.root not in final_path.parents:
            raise MediaSpoolError("Ruta de evidencia fuera del spool")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = final_path.with_suffix(".tmp")
        checksum = hashlib.sha256(processed.content).hexdigest()
        try:
            with temporary.open("xb") as stream:
                stream.write(processed.content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, final_path)
            created = utc_now()
            payload = {"media_id": media_id, "scan_id": scan_id,
                       "access_event_id": access_event_id, "media_type": media_type,
                       "checksum_sha256": checksum, "size_bytes": processed.bytes,
                       "format": processed.format, "schema_version": 1}
            with self.database.transaction() as connection:
                connection.execute(
                    """INSERT INTO local_media(id,scan_id,access_event_id,media_type,
                       relative_path,checksum_sha256,size_bytes,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,'PENDING',?,?)""",
                    (media_id, scan_id, access_event_id, media_type,
                     relative.as_posix(), checksum, processed.bytes, created, created),
                )
                connection.execute(
                    """INSERT INTO outbox(id,event_type,aggregate_type,aggregate_id,
                       payload_json,status,attempts,created_at,updated_at)
                       VALUES(?, 'MEDIA_READY','media',?,?,'PENDING',0,?,?)""",
                    (new_id(), media_id,
                     json.dumps(payload, separators=(",", ":")), created, created),
                )
        except (OSError, sqlite3.Error):
            temporary.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        return media_id

    def recover_abandoned(self) -> int:
        now = utc_now()
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT id FROM local_media WHERE status='IN_FLIGHT'"
            ).fetchall()
            ids = [row["id"] for row in rows]
            for media_id in ids:
                connection.execute(
                    """UPDATE local_media SET status='RETRY',next_attempt_at=?,
                       last_error='worker_restarted',updated_at=? WHERE id=?""",
                    (now, now, media_id),
                )
                connection.execute(
                    """UPDATE outbox SET status='RETRY',next_attempt_at=?,
                       last_error='worker_restarted',updated_at=?
                       WHERE event_type='MEDIA_READY' AND aggregate_id=?""",
                    (now, now, media_id),
                )
        return len(ids)

    def claim(self, limit: int) -> list[dict[str, Any]]:
        now = utc_now()
        with self.database.transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM local_media WHERE status IN ('PENDING','RETRY')
                   AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                   ORDER BY created_at,id LIMIT ?""", (now, limit)
            ).fetchall()
            ids = [row["id"] for row in rows]
            for media_id in ids:
                connection.execute(
                    """UPDATE local_media SET status='IN_FLIGHT',attempts=attempts+1,
                       updated_at=? WHERE id=?""", (now, media_id)
                )
                connection.execute(
                    """UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1,
                       updated_at=? WHERE event_type='MEDIA_READY' AND aggregate_id=?""",
                    (now, media_id),
                )
        return [dict(row) | {"attempts": int(row["attempts"]) + 1} for row in rows]

    def read_verified(self, row: dict[str, Any]) -> bytes:
        relative = Path(str(row["relative_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise MediaSpoolError("Ruta de evidencia insegura")
        path = (self.root / relative).resolve()
        if self.root not in path.parents or not path.is_file():
            raise MediaSpoolError("Archivo de evidencia faltante")
        content = path.read_bytes()
        if len(content) != row["size_bytes"]:
            raise MediaSpoolError("Tamano de evidencia incorrecto")
        if hashlib.sha256(content).hexdigest() != row["checksum_sha256"]:
            raise MediaSpoolError("Checksum de evidencia incorrecto")
        return content

    def complete(self, media_id: str, status: str, *, error: str | None = None,
                 delay_seconds: float = 0, max_attempts: int = 10) -> None:
        now = datetime.now(timezone.utc)
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT attempts FROM local_media WHERE id=?", (media_id,)
            ).fetchone()
            if not row:
                return
            if status in {"ACCEPTED", "DUPLICATE"}:
                target, next_at, synced_at = "SYNCED", None, now.isoformat()
            elif status == "PERMANENT_ERROR" or int(row["attempts"]) >= max_attempts:
                target, next_at, synced_at = "DEAD_LETTER", None, None
            else:
                target, synced_at = "RETRY", None
                next_at = (now + timedelta(seconds=delay_seconds)).isoformat()
            connection.execute(
                """UPDATE local_media SET status=?,next_attempt_at=?,last_error=?,
                   synced_at=?,updated_at=? WHERE id=?""",
                (target, next_at, error, synced_at, now.isoformat(), media_id),
            )
            connection.execute(
                """UPDATE outbox SET status=?,next_attempt_at=?,last_error=?,updated_at=?
                   WHERE event_type='MEDIA_READY' AND aggregate_id=?""",
                (target, next_at, error, now.isoformat(), media_id),
            )

    def stats(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(self.root)
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) total,COALESCE(SUM(size_bytes),0) bytes "
                "FROM local_media GROUP BY status"
            ).fetchall()
        counts = {row["status"]: int(row["total"]) for row in rows}
        return {"spool_path": str(self.root),
                "spool_bytes": sum(int(row["bytes"]) for row in rows),
                "disk_free_bytes": usage.free, "disk_total_bytes": usage.total,
                "low_space": usage.free < self.settings.media_min_free_bytes,
                "pending": counts.get("PENDING", 0),
                "in_flight": counts.get("IN_FLIGHT", 0),
                "retry": counts.get("RETRY", 0),
                "synced": counts.get("SYNCED", 0),
                "dead_letters": counts.get("DEAD_LETTER", 0)}
