from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from edge_agent.db.migrations import MIGRATIONS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EdgeDatabase:
    def __init__(self, path: Path, busy_timeout_ms: int = 5000) -> None:
        self.path = path.expanduser().resolve()
        self.busy_timeout_ms = busy_timeout_ms

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_ms)}")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
        for migration in MIGRATIONS:
            with self.transaction() as connection:
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?",
                    (migration.version,),
                ).fetchone()
                if applied:
                    continue
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, utc_now()),
                )
                connection.execute(f"PRAGMA user_version = {migration.version}")

    def diagnostics(self) -> dict[str, object]:
        with self.connection() as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        return {
            "ready": True,
            "journal_mode": str(journal_mode).lower(),
            "foreign_keys": bool(foreign_keys),
            "busy_timeout_ms": int(busy_timeout),
            "schema_version": int(version),
        }
