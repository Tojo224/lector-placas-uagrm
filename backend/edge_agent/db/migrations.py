from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(
        version=1,
        name="initial_edge_operational_schema",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS cached_people (
                id TEXT PRIMARY KEY,
                central_id TEXT UNIQUE,
                university_code TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                person_type TEXT,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                source_updated_at TEXT,
                cached_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cached_vehicles (
                id TEXT PRIMARY KEY,
                central_id TEXT UNIQUE NOT NULL,
                plate TEXT UNIQUE NOT NULL,
                owner_person_id TEXT REFERENCES cached_people(id) ON DELETE SET NULL,
                owner_name TEXT,
                brand_name TEXT,
                vehicle_type_name TEXT,
                color TEXT,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                source_updated_at TEXT,
                cached_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cached_devices (
                id TEXT PRIMARY KEY,
                central_id TEXT UNIQUE,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                direction TEXT CHECK (direction IN ('ENTRY', 'EXIT', 'AUTO')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                source_updated_at TEXT,
                cached_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS edge_scans (
                id TEXT PRIMARY KEY,
                detected_plate TEXT,
                normalized_plate TEXT,
                confidence REAL,
                status TEXT NOT NULL,
                device_id TEXT REFERENCES cached_devices(id) ON DELETE SET NULL,
                vehicle_id TEXT REFERENCES cached_vehicles(id) ON DELETE SET NULL,
                realtime INTEGER NOT NULL DEFAULT 0 CHECK (realtime IN (0, 1)),
                captured_at TEXT NOT NULL,
                synced_at TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_edge_scans_pending ON edge_scans(synced_at, captured_at)",
            "CREATE INDEX IF NOT EXISTS ix_edge_scans_plate ON edge_scans(normalized_plate)",
            """
            CREATE TABLE IF NOT EXISTS edge_access_events (
                id TEXT PRIMARY KEY,
                scan_id TEXT UNIQUE NOT NULL REFERENCES edge_scans(id) ON DELETE RESTRICT,
                vehicle_id TEXT REFERENCES cached_vehicles(id) ON DELETE SET NULL,
                device_id TEXT REFERENCES cached_devices(id) ON DELETE SET NULL,
                direction TEXT NOT NULL CHECK (direction IN ('ENTRY', 'EXIT')),
                decision TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                occurred_at TEXT NOT NULL,
                synced_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS vehicle_presence (
                vehicle_id TEXT PRIMARY KEY REFERENCES cached_vehicles(id) ON DELETE CASCADE,
                state TEXT NOT NULL CHECK (state IN ('INSIDE', 'OUTSIDE', 'UNKNOWN')),
                last_access_event_id TEXT REFERENCES edge_access_events(id) ON DELETE SET NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS local_media (
                id TEXT PRIMARY KEY,
                scan_id TEXT REFERENCES edge_scans(id) ON DELETE SET NULL,
                access_event_id TEXT REFERENCES edge_access_events(id) ON DELETE SET NULL,
                media_type TEXT NOT NULL,
                relative_path TEXT UNIQUE NOT NULL,
                checksum_sha256 TEXT,
                size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                synced_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'IN_FLIGHT', 'RETRY', 'SYNCED', 'DEAD_LETTER')),
                attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                next_attempt_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_outbox_pending ON outbox(status, next_attempt_at, created_at)",
            """
            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
    Migration(
        version=2,
        name="durable_media_sync_state",
        statements=(
            "ALTER TABLE local_media ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE local_media ADD COLUMN next_attempt_at TEXT",
            "ALTER TABLE local_media ADD COLUMN last_error TEXT",
            "ALTER TABLE local_media ADD COLUMN updated_at TEXT",
            "CREATE INDEX IF NOT EXISTS ix_local_media_sync ON local_media(status, next_attempt_at, created_at)",
        ),
    ),
    Migration(
        version=3,
        name="local_staff_auth_verifiers",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS local_auth_users (
                central_user_id TEXT PRIMARY KEY,
                carnet TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('ADMINISTRADOR', 'OPERADOR')),
                local_verifier TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_online_auth_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_local_auth_users_carnet ON local_auth_users(carnet)",
            "DELETE FROM local_auth_users WHERE role NOT IN ('ADMINISTRADOR', 'OPERADOR')",
        ),
    ),
)
