from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath
from typing import Any

from edge_agent.db.database import EdgeDatabase, utc_now

_SENSITIVE_KEY_PARTS = (
    "password",
    "contrasena",
    "secret",
    "token",
    "jwt",
    "credential",
    "cloudinary",
    "api_key",
)


def new_id() -> str:
    return str(uuid.uuid4())


def _ensure_safe_key(key: str) -> None:
    normalized = key.lower()
    if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
        raise ValueError("No se permite persistir claves sensibles en SQLite.")


def _ensure_safe_payload(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _ensure_safe_key(str(key))
            _ensure_safe_payload(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _ensure_safe_payload(child)


def _relative_media_path(value: str) -> str:
    path = PurePath(value)
    if path.is_absolute() or ".." in path.parts or not value.strip():
        raise ValueError("local_media requiere una ruta relativa segura.")
    return Path(*path.parts).as_posix()


class CachedVehicleRepository:
    def __init__(self, database: EdgeDatabase) -> None:
        self.database = database

    def upsert(
        self,
        *,
        central_id: str,
        plate: str,
        is_active: bool = True,
        owner_name: str | None = None,
        brand_name: str | None = None,
        vehicle_type_name: str | None = None,
        color: str | None = None,
        source_updated_at: str | None = None,
    ) -> str:
        now = utc_now()
        local_id = new_id()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO cached_vehicles(
                    id, central_id, plate, owner_name, brand_name,
                    vehicle_type_name, color, is_active, source_updated_at, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(central_id) DO UPDATE SET
                    plate=excluded.plate,
                    owner_name=excluded.owner_name,
                    brand_name=excluded.brand_name,
                    vehicle_type_name=excluded.vehicle_type_name,
                    color=excluded.color,
                    is_active=excluded.is_active,
                    source_updated_at=excluded.source_updated_at,
                    cached_at=excluded.cached_at
                """,
                (
                    local_id,
                    central_id,
                    plate.replace("-", "").replace(" ", "").upper(),
                    owner_name,
                    brand_name,
                    vehicle_type_name,
                    color,
                    int(is_active),
                    source_updated_at,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id FROM cached_vehicles WHERE central_id = ?", (central_id,)
            ).fetchone()
        return str(row["id"])

    def get_by_plate(self, plate: str) -> dict[str, Any] | None:
        normalized = plate.replace("-", "").replace(" ", "").upper()
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM cached_vehicles WHERE plate = ?", (normalized,)
            ).fetchone()
        return dict(row) if row else None


class ScanRepository:
    def __init__(self, database: EdgeDatabase) -> None:
        self.database = database

    def create_from_ocr(
        self, result: dict[str, Any], realtime: bool, captured_at: str | None = None
    ) -> str:
        scan_id = new_id()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO edge_scans(
                    id, detected_plate, normalized_plate, confidence,
                    status, realtime, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    result.get("detected_plate"),
                    result.get("normalized_plate"),
                    result.get("combined_confidence"),
                    str(result.get("status") or "ERROR"),
                    int(realtime),
                    captured_at or utc_now(),
                ),
            )
        return scan_id

    def get(self, scan_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM edge_scans WHERE id = ?", (scan_id,)
            ).fetchone()
        return dict(row) if row else None

    def count(self) -> int:
        with self.database.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM edge_scans").fetchone()[0])


class AccessEventRepository:
    def __init__(self, database: EdgeDatabase) -> None:
        self.database = database

    def create(
        self,
        *,
        scan_id: str,
        direction: str,
        decision: str,
        vehicle_id: str | None = None,
        device_id: str | None = None,
    ) -> str:
        event_id = new_id()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO edge_access_events(
                    id, scan_id, vehicle_id, device_id, direction,
                    decision, status, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    event_id,
                    scan_id,
                    vehicle_id,
                    device_id,
                    direction,
                    decision,
                    utc_now(),
                ),
            )
        return event_id


class OutboxRepository:
    def __init__(self, database: EdgeDatabase) -> None:
        self.database = database

    def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> str:
        _ensure_safe_payload(payload)
        outbox_id = new_id()
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO outbox(
                    id, event_type, aggregate_type, aggregate_id, payload_json,
                    status, attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
                """,
                (
                    outbox_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        return outbox_id

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM outbox
                WHERE status IN ('PENDING', 'RETRY')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at, id
                LIMIT ?
                """,
                (utc_now(), limit),
            ).fetchall()
        return [dict(row) | {"payload": json.loads(row["payload_json"])} for row in rows]

    def mark_synced(self, outbox_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE outbox SET status='SYNCED', updated_at=? WHERE id=?",
                (utc_now(), outbox_id),
            )

    def recover_abandoned(self) -> int:
        now = utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """UPDATE outbox SET status='RETRY', next_attempt_at=?,
                   last_error='worker_restarted', updated_at=?
                   WHERE status='IN_FLIGHT'""",
                (now, now),
            )
        return cursor.rowcount

    def claim(self, limit: int) -> list[dict[str, Any]]:
        now = utc_now()
        with self.database.transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM outbox WHERE status IN ('PENDING','RETRY')
                   AND event_type <> 'MEDIA_READY'
                   AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                   ORDER BY created_at,id LIMIT ?""", (now, limit)
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(
                    f"UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1,"
                    f"updated_at=? WHERE id IN ({placeholders})", (now, *ids)
                )
        return [dict(row) | {"payload": json.loads(row["payload_json"]),
                             "attempts": int(row["attempts"]) + 1} for row in rows]

    def complete(self, outbox_id: str, status: str, *, error: str | None = None,
                 retry_delay_seconds: float | None = None,
                 max_attempts: int = 10) -> None:
        now = datetime.now(timezone.utc)
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT attempts,aggregate_type,aggregate_id FROM outbox WHERE id=?",
                (outbox_id,),
            ).fetchone()
            if not row:
                return
            if status in {"ACCEPTED", "DUPLICATE"}:
                target, next_at = "SYNCED", None
            elif status == "PERMANENT_ERROR" or int(row["attempts"]) >= max_attempts:
                target, next_at = "DEAD_LETTER", None
            else:
                target = "RETRY"
                next_at = (now + timedelta(seconds=retry_delay_seconds or 0)).isoformat()
            connection.execute(
                """UPDATE outbox SET status=?,next_attempt_at=?,last_error=?,updated_at=?
                   WHERE id=?""", (target, next_at, error, now.isoformat(), outbox_id)
            )
            if target == "SYNCED" and row["aggregate_type"] == "scan":
                connection.execute(
                    "UPDATE edge_scans SET synced_at=? WHERE id=?",
                    (now.isoformat(), row["aggregate_id"]),
                )
            elif target == "SYNCED" and row["aggregate_type"] == "access_event":
                connection.execute(
                    "UPDATE edge_access_events SET status='SYNCED',synced_at=? WHERE id=?",
                    (now.isoformat(), row["aggregate_id"]),
                )

    def counts(self) -> dict[str, int]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) AS total FROM outbox GROUP BY status"
            ).fetchall()
        values = {row["status"]: int(row["total"]) for row in rows}
        return {"pending": values.get("PENDING", 0) + values.get("IN_FLIGHT", 0),
                "retry": values.get("RETRY", 0),
                "dead_letters": values.get("DEAD_LETTER", 0),
                "synced": values.get("SYNCED", 0)}


class LocalMediaRepository:
    def __init__(self, database: EdgeDatabase) -> None:
        self.database = database

    def create(
        self,
        *,
        relative_path: str,
        media_type: str,
        scan_id: str | None = None,
        access_event_id: str | None = None,
        checksum_sha256: str | None = None,
        size_bytes: int | None = None,
    ) -> str:
        media_id = new_id()
        safe_path = _relative_media_path(relative_path)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO local_media(
                    id, scan_id, access_event_id, media_type, relative_path,
                    checksum_sha256, size_bytes, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    media_id,
                    scan_id,
                    access_event_id,
                    media_type,
                    safe_path,
                    checksum_sha256,
                    size_bytes,
                    utc_now(),
                ),
            )
        return media_id


class StateRepository:
    def __init__(self, database: EdgeDatabase) -> None:
        self.database = database

    def _set(self, table: str, key: str, value: str | None) -> None:
        _ensure_safe_key(key)
        if table not in {"sync_state", "agent_metadata"}:
            raise ValueError("Tabla de estado no permitida.")
        with self.database.transaction() as connection:
            connection.execute(
                f"""
                INSERT INTO {table}(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, utc_now()),
            )

    def _get(self, table: str, key: str) -> str | None:
        with self.database.connection() as connection:
            row = connection.execute(
                f"SELECT value FROM {table} WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row and row["value"] is not None else None

    def set_sync(self, key: str, value: str | None) -> None:
        self._set("sync_state", key, value)

    def get_sync(self, key: str) -> str | None:
        return self._get("sync_state", key)

    def set_metadata(self, key: str, value: str | None) -> None:
        self._set("agent_metadata", key, value)

    def get_metadata(self, key: str) -> str | None:
        return self._get("agent_metadata", key)
