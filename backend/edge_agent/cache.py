from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from edge_agent.db import EdgeDatabase
from edge_agent.db.database import utc_now


def _normalized_plate(value: str) -> str:
    return value.replace("-", "").replace(" ", "").upper()


def apply_snapshot(database: EdgeDatabase, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Replace the operational projection atomically while preserving retained presence."""
    now = utc_now()
    vehicles = snapshot.get("vehicles", [])
    devices = snapshot.get("devices", [])
    with database.transaction() as connection:
        vehicle_ids: list[str] = []
        for item in vehicles:
            central_id = str(item["central_id"])
            vehicle_ids.append(central_id)
            connection.execute(
                """
                INSERT INTO cached_vehicles(
                    id, central_id, plate, owner_name, brand_name,
                    vehicle_type_name, color, is_active, source_updated_at, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(central_id) DO UPDATE SET plate=excluded.plate,
                    owner_name=excluded.owner_name, brand_name=excluded.brand_name,
                    vehicle_type_name=excluded.vehicle_type_name, color=excluded.color,
                    is_active=excluded.is_active,
                    source_updated_at=excluded.source_updated_at, cached_at=excluded.cached_at
                """,
                (str(uuid.uuid4()), central_id, _normalized_plate(item["plate"]),
                 item.get("owner_name"), item.get("brand_name"),
                 item.get("vehicle_type_name"), item.get("color"),
                 int(item.get("is_active", True)), item.get("source_updated_at"), now),
            )
        if vehicle_ids:
            placeholders = ",".join("?" for _ in vehicle_ids)
            connection.execute(
                f"DELETE FROM cached_vehicles WHERE central_id NOT IN ({placeholders})",
                vehicle_ids,
            )
        else:
            connection.execute("DELETE FROM cached_vehicles")

        device_ids: list[str] = []
        for item in devices:
            central_id = str(item["central_id"])
            device_ids.append(central_id)
            connection.execute(
                """
                INSERT INTO cached_devices(
                    id, central_id, name, location, direction, is_active,
                    source_updated_at, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(central_id) DO UPDATE SET name=excluded.name,
                    location=excluded.location, direction=excluded.direction,
                    is_active=excluded.is_active,
                    source_updated_at=excluded.source_updated_at, cached_at=excluded.cached_at
                """,
                (str(uuid.uuid4()), central_id, item["name"], item["location"],
                 item.get("direction", "AUTO"), int(item.get("is_active", True)),
                 item.get("source_updated_at"), now),
            )
        if device_ids:
            placeholders = ",".join("?" for _ in device_ids)
            connection.execute(
                f"DELETE FROM cached_devices WHERE central_id NOT IN ({placeholders})",
                device_ids,
            )
        else:
            connection.execute("DELETE FROM cached_devices")

        state = {
            "snapshot_version": str(snapshot["version"]),
            "snapshot_generated_at": str(snapshot["generated_at"]),
            "snapshot_applied_at": now,
        }
        for key, value in state.items():
            connection.execute(
                """INSERT INTO sync_state(key,value,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                    updated_at=excluded.updated_at""",
                (key, value, now),
            )
    return {"version": state["snapshot_version"], "vehicles": len(vehicles),
            "devices": len(devices), "applied_at": now}


def cache_status(database: EdgeDatabase, max_age_hours: float) -> dict[str, Any]:
    with database.connection() as connection:
        row = connection.execute(
            "SELECT value FROM sync_state WHERE key='snapshot_generated_at'"
        ).fetchone()
    if not row or not row["value"]:
        return {"valid": False, "state": "MISSING", "age_hours": None}
    try:
        generated = datetime.fromisoformat(str(row["value"]).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - generated).total_seconds() / 3600)
    except ValueError:
        return {"valid": False, "state": "INVALID", "age_hours": None}
    return {"valid": age <= max_age_hours,
            "state": "FRESH" if age <= max_age_hours else "STALE",
            "age_hours": round(age, 3)}
