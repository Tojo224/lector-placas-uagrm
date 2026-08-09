from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from edge_agent.config import EdgeSettings
from edge_agent.db.database import EdgeDatabase
from edge_agent.db.repositories import (
    AccessEventRepository,
    CachedVehicleRepository,
    LocalMediaRepository,
    OutboxRepository,
    ScanRepository,
    StateRepository,
)

EXPECTED_TABLES = {
    "cached_vehicles",
    "cached_people",
    "cached_devices",
    "vehicle_presence",
    "edge_scans",
    "edge_access_events",
    "local_media",
    "outbox",
    "sync_state",
    "agent_metadata",
    "schema_migrations",
}


def database_at(tmp_path) -> EdgeDatabase:
    database = EdgeDatabase(tmp_path / "data" / "edge.sqlite3", 5000)
    database.initialize()
    return database


def test_creates_minimal_schema_and_pragmas_from_scratch(tmp_path):
    database = database_at(tmp_path)
    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO edge_access_events(
                    id, scan_id, direction, decision, status, occurred_at
                ) VALUES ('event', 'missing-scan', 'ENTRY', 'ALLOW', 'PENDING', 'now')
                """
            )

    diagnostics = database.diagnostics()
    assert EXPECTED_TABLES <= tables
    assert diagnostics["journal_mode"] == "wal"
    assert diagnostics["foreign_keys"] is True
    assert diagnostics["busy_timeout_ms"] == 5000
    assert diagnostics["schema_version"] == 2


def test_migrations_are_versioned_and_idempotent(tmp_path):
    database = database_at(tmp_path)
    database.initialize()
    database.initialize()
    with database.connection() as connection:
        migrations = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert [(row["version"], row["name"]) for row in migrations] == [
        (1, "initial_edge_operational_schema"),
        (2, "durable_media_sync_state"),
    ]


def test_repositories_survive_database_reopen_and_recover_pending(tmp_path):
    path = tmp_path / "persistent" / "edge.sqlite3"
    first = EdgeDatabase(path)
    first.initialize()
    vehicles = CachedVehicleRepository(first)
    scans = ScanRepository(first)
    outbox = OutboxRepository(first)
    state = StateRepository(first)

    vehicle_id = vehicles.upsert(central_id="central-1", plate="1234-ABC")
    scan_id = scans.create_from_ocr(
        {
            "status": "DETECTED",
            "detected_plate": "1234-ABC",
            "normalized_plate": "1234ABC",
            "combined_confidence": 0.91,
        },
        realtime=False,
    )
    outbox_id = outbox.enqueue(
        event_type="SCAN_CREATED",
        aggregate_type="scan",
        aggregate_id=scan_id,
        payload={"scan_id": scan_id},
    )
    state.set_sync("catalog_cursor", "cursor-1")
    state.set_metadata("installation_id", "installation-1")

    reopened = EdgeDatabase(path)
    reopened.initialize()
    pending = OutboxRepository(reopened).pending()
    assert CachedVehicleRepository(reopened).get_by_plate("1234ABC")["id"] == vehicle_id
    assert ScanRepository(reopened).get(scan_id)["status"] == "DETECTED"
    assert pending[0]["id"] == outbox_id
    assert pending[0]["payload"] == {"scan_id": scan_id}
    assert StateRepository(reopened).get_sync("catalog_cursor") == "cursor-1"
    assert StateRepository(reopened).get_metadata("installation_id") == "installation-1"


def test_access_and_media_repositories_enforce_relations_and_relative_paths(tmp_path):
    database = database_at(tmp_path)
    scan_id = ScanRepository(database).create_from_ocr(
        {"status": "LOW_CONFIDENCE"}, realtime=True
    )
    event_id = AccessEventRepository(database).create(
        scan_id=scan_id,
        direction="ENTRY",
        decision="MANUAL_REVIEW",
    )
    media_id = LocalMediaRepository(database).create(
        scan_id=scan_id,
        access_event_id=event_id,
        relative_path="media/2026/evidence.webp",
        media_type="ACCESS_ENTRY",
        size_bytes=128,
    )
    assert event_id and media_id
    with pytest.raises(ValueError, match="ruta relativa"):
        LocalMediaRepository(database).create(
            relative_path=str(tmp_path / "absolute.webp"),
            media_type="ACCESS_ENTRY",
        )


def test_moderate_concurrency_does_not_lock_database(tmp_path):
    database = database_at(tmp_path)

    def write_scan(index: int) -> str:
        return ScanRepository(database).create_from_ocr(
            {
                "status": "LOW_CONFIDENCE",
                "detected_plate": f"TEST{index:04d}",
                "combined_confidence": 0.40,
            },
            realtime=True,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(write_scan, range(160)))

    assert len(set(ids)) == 160
    assert ScanRepository(database).count() == 160


def test_data_path_is_configurable_and_not_relative_to_source(tmp_path, monkeypatch):
    configured = tmp_path / "external-agent-data"
    monkeypatch.setenv("EDGE_DATA_DIR", str(configured))
    monkeypatch.chdir(tmp_path)
    settings = EdgeSettings.from_env()
    assert settings.database_path() == (
        configured / "data" / "edge-agent.sqlite3"
    ).resolve()


def test_schema_and_repositories_reject_sensitive_storage(tmp_path):
    database = database_at(tmp_path)
    forbidden = ("password", "contrasena", "secret", "token", "jwt", "cloudinary")
    with database.connection() as connection:
        for table in EXPECTED_TABLES:
            columns = [row["name"].lower() for row in connection.execute(f"PRAGMA table_info({table})")]
            assert not any(part in column for column in columns for part in forbidden)

    with pytest.raises(ValueError, match="sensibles"):
        OutboxRepository(database).enqueue(
            event_type="INVALID",
            aggregate_type="test",
            aggregate_id="1",
            payload={"jwt_token": "must-not-be-stored"},
        )
    with pytest.raises(ValueError, match="sensibles"):
        StateRepository(database).set_metadata("cloudinary_secret", "invalid")
