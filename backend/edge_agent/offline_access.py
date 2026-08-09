from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.services.access_decision import infer_access_type

from edge_agent.cache import cache_status
from edge_agent.db import EdgeDatabase
from edge_agent.db.database import utc_now
from edge_agent.db.repositories import _ensure_safe_payload, new_id


def is_relevant_ocr(result: dict[str, Any]) -> bool:
    status = result.get("status")
    return bool(
        (status == "DETECTED" and result.get("normalized_plate"))
        or (status == "LOW_CONFIDENCE" and
            (result.get("detected_plate") or result.get("plate_bbox")))
    )


class OfflineAccessService:
    def __init__(self, database: EdgeDatabase, max_age_hours: float,
                 duplicate_cooldown_seconds: int = 30) -> None:
        self.database = database
        self.max_age_hours = max_age_hours
        self.duplicate_cooldown_seconds = duplicate_cooldown_seconds

    def cache_status(self) -> dict[str, Any]:
        return cache_status(self.database, self.max_age_hours)

    def process(self, result: dict[str, Any], realtime: bool,
                device_central_id: str | None = None) -> dict[str, Any]:
        if not is_relevant_ocr(result):
            return self._outcome("NO_RELEVANT_OCR", "Frame sin OCR relevante.")
        status = result.get("status")
        if status != "DETECTED" or not result.get("normalized_plate"):
            return self._record_denial(result, realtime, "MANUAL_REVIEW",
                                       "Lectura dudosa; requiere revision manual.")

        freshness = self.cache_status()
        if freshness["state"] == "MISSING":
            return self._record_denial(result, realtime, "DENY_CACHE_MISSING",
                                       "No existe un snapshot operativo local.")
        if not freshness["valid"]:
            return self._record_denial(result, realtime, "DENY_CACHE_STALE",
                                       "El snapshot operativo local esta vencido.")

        plate = str(result["normalized_plate"]).replace("-", "").replace(" ", "").upper()
        with self.database.transaction() as connection:
            vehicle = connection.execute(
                "SELECT * FROM cached_vehicles WHERE plate=?", (plate,)
            ).fetchone()
            if not vehicle:
                return self._record_denial_in(connection, result, realtime,
                                              "DENY_UNKNOWN", "Placa desconocida.")
            if not vehicle["is_active"]:
                return self._record_denial_in(connection, result, realtime,
                                              "DENY_INACTIVE", "Vehiculo inactivo.", vehicle)
            if device_central_id:
                device = connection.execute(
                    "SELECT * FROM cached_devices WHERE central_id=? AND is_active=1",
                    (device_central_id,),
                ).fetchone()
            else:
                device = connection.execute(
                    "SELECT * FROM cached_devices WHERE is_active=1 ORDER BY name LIMIT 1"
                ).fetchone()
            if not device:
                return self._record_denial_in(connection, result, realtime,
                                              "DENY_DEVICE", "Dispositivo local no provisionado.", vehicle)

            last = connection.execute(
                "SELECT occurred_at FROM edge_access_events WHERE vehicle_id=? "
                "ORDER BY occurred_at DESC LIMIT 1", (vehicle["id"],)
            ).fetchone()
            if last and self.duplicate_cooldown_seconds > 0:
                occurred = datetime.fromisoformat(last["occurred_at"])
                elapsed = (datetime.now(timezone.utc) - occurred).total_seconds()
                if elapsed < self.duplicate_cooldown_seconds:
                    return self._outcome("DUPLICATE", "Lectura repetida dentro del cooldown.",
                                         vehicle=vehicle, persisted=False)

            presence = connection.execute(
                "SELECT state FROM vehicle_presence WHERE vehicle_id=?", (vehicle["id"],)
            ).fetchone()
            campus_state = "DENTRO" if presence and presence["state"] == "INSIDE" else "FUERA"
            direction = infer_access_type(device["name"], campus_state)
            internal_direction = "ENTRY" if direction == "ENTRADA" else "EXIT"
            next_presence = "INSIDE" if internal_direction == "ENTRY" else "OUTSIDE"
            scan_id = self._insert_scan(connection, result, realtime, vehicle["id"], device["id"])
            event_id = new_id()
            now = utc_now()
            connection.execute(
                """INSERT INTO edge_access_events(id,scan_id,vehicle_id,device_id,direction,
                   decision,status,occurred_at) VALUES(?,?,?,?,?,'ALLOW','PENDING',?)""",
                (event_id, scan_id, vehicle["id"], device["id"], internal_direction, now),
            )
            connection.execute(
                """INSERT INTO vehicle_presence(vehicle_id,state,last_access_event_id,updated_at)
                   VALUES(?,?,?,?) ON CONFLICT(vehicle_id) DO UPDATE SET
                   state=excluded.state,last_access_event_id=excluded.last_access_event_id,
                   updated_at=excluded.updated_at""",
                (vehicle["id"], next_presence, event_id, now),
            )
            self._insert_outbox(connection, "ACCESS_DECIDED", "access_event", event_id,
                                {"access_event_id": event_id, "scan_id": scan_id,
                                 "vehicle_central_id": vehicle["central_id"],
                                 "device_central_id": device["central_id"],
                                 "direction": direction, "decision": "ALLOW",
                                 "occurred_at": now})
            return self._outcome("ALLOW", "Acceso autorizado por cache local.", vehicle,
                                 direction, event_id, True, scan_id)

    def _record_denial(self, result: dict[str, Any], realtime: bool,
                       decision: str, reason: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            return self._record_denial_in(connection, result, realtime, decision, reason)

    def _record_denial_in(self, connection, result, realtime, decision, reason, vehicle=None):
        scan_id = self._insert_scan(connection, result, realtime,
                                    vehicle["id"] if vehicle else None, None)
        self._insert_outbox(connection, "SCAN_RECORDED", "scan", scan_id,
                            {"scan_id": scan_id, "plate": result.get("normalized_plate"),
                             "confidence": result.get("combined_confidence"),
                             "status": result.get("status"), "decision": decision,
                             "captured_at": utc_now()})
        return self._outcome(decision, reason, vehicle=vehicle, persisted=True,
                             scan_id=scan_id)

    @staticmethod
    def _insert_scan(connection, result, realtime, vehicle_id=None, device_id=None):
        scan_id = new_id()
        connection.execute(
            """INSERT INTO edge_scans(id,detected_plate,normalized_plate,confidence,status,
               device_id,vehicle_id,realtime,captured_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (scan_id, result.get("detected_plate"), result.get("normalized_plate"),
             result.get("combined_confidence"), str(result.get("status") or "ERROR"),
             device_id, vehicle_id, int(realtime), utc_now()),
        )
        return scan_id

    @staticmethod
    def _insert_outbox(connection, event_type, aggregate_type, aggregate_id, payload):
        _ensure_safe_payload(payload)
        now = utc_now()
        connection.execute(
            """INSERT INTO outbox(id,event_type,aggregate_type,aggregate_id,payload_json,
               status,attempts,created_at,updated_at) VALUES(?,?,?,?,?,'PENDING',0,?,?)""",
            (new_id(), event_type, aggregate_type, aggregate_id,
             json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now, now),
        )

    @staticmethod
    def _outcome(decision, reason, vehicle=None, direction=None, event_id=None,
                 persisted=False, scan_id=None):
        return {"decision": decision, "reason": reason,
                "offline_state": "LOCAL_AUTHORIZED" if decision == "ALLOW" else "LOCAL_DENIED",
                "vehicle_found": vehicle is not None,
                "vehicle_central_id": vehicle["central_id"] if vehicle else None,
                "vehicle_owner_name": vehicle["owner_name"] if vehicle else None,
                "direction": direction, "access_event_id": event_id,
                "scan_id": scan_id, "persisted": persisted}
