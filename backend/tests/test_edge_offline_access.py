from __future__ import annotations

import socket
from datetime import datetime, timedelta, timezone

from edge_agent.cache import apply_snapshot
from edge_agent.db import EdgeDatabase
from edge_agent.offline_access import OfflineAccessService


def snapshot(*, active: bool = True, generated_at: str | None = None):
    return {
        "version": "snapshot-1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "vehicles": [{"central_id": "vehicle-1", "plate": "1234ABC",
                      "is_active": active, "owner_name": "Ana Perez"}],
        "devices": [{"central_id": "device-1", "name": "Porton Principal",
                     "location": "Campus", "direction": "ENTRY", "is_active": True}],
    }


def detected(plate="1234ABC"):
    return {"status": "DETECTED", "detected_plate": plate,
            "normalized_plate": plate, "combined_confidence": 0.93}


def count(db, table):
    with db.connection() as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_snapshot_is_atomic_and_survives_restart(tmp_path):
    path = tmp_path / "portable" / "edge.sqlite3"
    db = EdgeDatabase(path)
    db.initialize()
    result = apply_snapshot(db, snapshot())
    assert result["vehicles"] == 1
    restarted = EdgeDatabase(path)
    restarted.initialize()
    with restarted.connection() as connection:
        assert connection.execute(
            "SELECT plate FROM cached_vehicles WHERE central_id='vehicle-1'"
        ).fetchone()["plate"] == "1234ABC"
        assert connection.execute(
            "SELECT value FROM sync_state WHERE key='snapshot_version'"
        ).fetchone()["value"] == "snapshot-1"


def test_active_vehicle_toggles_presence_and_persists_atomic_event(tmp_path):
    db = EdgeDatabase(tmp_path / "edge.sqlite3")
    db.initialize()
    apply_snapshot(db, snapshot())
    service = OfflineAccessService(db, 24, duplicate_cooldown_seconds=0)

    first = service.process(detected(), True, "device-1")
    second = service.process(detected(), True, "device-1")
    assert (first["decision"], first["direction"]) == ("ALLOW", "ENTRADA")
    assert (second["decision"], second["direction"]) == ("ALLOW", "SALIDA")
    with db.connection() as connection:
        presence = connection.execute("SELECT state FROM vehicle_presence").fetchone()
    assert presence["state"] == "OUTSIDE"
    assert count(db, "edge_scans") == 2
    assert count(db, "edge_access_events") == 2
    assert count(db, "outbox") == 2

    restarted = EdgeDatabase(db.path)
    restarted.initialize()
    with restarted.connection() as connection:
        assert connection.execute("SELECT state FROM vehicle_presence").fetchone()["state"] == "OUTSIDE"


def test_unknown_inactive_missing_and_stale_cache_fail_closed(tmp_path):
    cases = []
    for name in ("unknown", "inactive", "missing", "stale"):
        db = EdgeDatabase(tmp_path / name / "edge.sqlite3")
        db.initialize()
        if name != "missing":
            generated = ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
                         if name == "stale" else None)
            apply_snapshot(db, snapshot(active=name != "inactive", generated_at=generated))
        service = OfflineAccessService(db, 24)
        result = service.process(detected("9999ZZZ" if name == "unknown" else "1234ABC"), True)
        cases.append(result["decision"])
        assert result["decision"] != "ALLOW"
        assert count(db, "cached_vehicles") == (0 if name == "missing" else 1)
    assert cases == ["DENY_UNKNOWN", "DENY_INACTIVE", "DENY_CACHE_MISSING", "DENY_CACHE_STALE"]


def test_empty_polling_and_duplicates_do_not_grow_scans(tmp_path):
    db = EdgeDatabase(tmp_path / "edge.sqlite3")
    db.initialize()
    apply_snapshot(db, snapshot())
    service = OfflineAccessService(db, 24, duplicate_cooldown_seconds=60)
    empty = {"status": "LOW_CONFIDENCE", "detected_plate": None,
             "normalized_plate": None, "combined_confidence": None}
    for _ in range(100):
        assert service.process(empty, True)["decision"] == "NO_RELEVANT_OCR"
    assert count(db, "edge_scans") == 0
    assert service.process(detected(), True)["decision"] == "ALLOW"
    assert service.process(detected(), True)["decision"] == "DUPLICATE"
    assert count(db, "edge_scans") == 1


def test_local_decision_does_not_open_network_connections(tmp_path, monkeypatch):
    db = EdgeDatabase(tmp_path / "edge.sqlite3")
    db.initialize()
    apply_snapshot(db, snapshot())
    service = OfflineAccessService(db, 24, duplicate_cooldown_seconds=0)

    def blocked_connect(*_args, **_kwargs):
        raise AssertionError("La decision local intento usar la red")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    assert service.process(detected(), True)["decision"] == "ALLOW"
