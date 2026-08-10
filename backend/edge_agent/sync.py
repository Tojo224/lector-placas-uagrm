from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from edge_agent.cache import apply_snapshot
from edge_agent.config import EdgeSettings
from edge_agent.db import EdgeDatabase
from edge_agent.db.repositories import OutboxRepository, StateRepository
from edge_agent.media_spool import MediaSpool, MediaSpoolError


class SyncWorker:
    def __init__(self, database: EdgeDatabase, settings: EdgeSettings,
                 client: httpx.AsyncClient | None = None) -> None:
        self.database = database
        self.settings = settings
        self.outbox = OutboxRepository(database)
        self.state = StateRepository(database)
        self.media = MediaSpool(database, settings)
        self.client = client
        self._owns_client = client is None
        self._stop = asyncio.Event()
        self.online = False
        self.last_error: str | None = None
        self.next_attempt_at: datetime | None = None

    def _headers(self) -> dict[str, str]:
        if self.settings.installation_id and self.settings.installation_key:
            return {
                "X-Edge-Installation-ID": str(self.settings.installation_id),
                "Authorization": f"Bearer {self.settings.installation_key}",
            }
        return {
            "X-Edge-Device-ID": str(self.settings.device_id),
            "Authorization": f"Bearer {self.settings.device_key}",
        }

    async def run(self) -> None:
        await asyncio.to_thread(self.outbox.recover_abandoned)
        await asyncio.to_thread(self.media.recover_abandoned)
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=str(self.settings.central_url).rstrip("/"),
                timeout=self.settings.sync_timeout_seconds,
                headers=self._headers(),
            )
        try:
            while not self._stop.is_set():
                await self.run_once()
                self.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=self.settings.sync_poll_seconds)
                try:
                    await asyncio.wait_for(self._stop.wait(), self.settings.sync_poll_seconds)
                except TimeoutError:
                    pass
        finally:
            if self._owns_client and self.client:
                await self.client.aclose()

    def stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> None:
        errors: list[Exception] = []
        contacted = False
        try:
            contacted = await self._refresh_snapshot_if_due() or contacted
        except (httpx.HTTPError, TypeError, ValueError, KeyError) as exc:
            errors.append(exc)
        try:
            contacted = await self._flush_outbox() or contacted
        except (httpx.HTTPError, TypeError, ValueError, KeyError) as exc:
            errors.append(exc)
        try:
            contacted = await self._flush_media() or contacted
        except (httpx.HTTPError, TypeError, ValueError, KeyError) as exc:
            errors.append(exc)
        if not errors and contacted:
            self.online = True
            self.last_error = None
            self.state.set_sync("last_sync_success_at", datetime.now(timezone.utc).isoformat())
        elif errors:
            self.online = False
            self.last_error = type(errors[0]).__name__

    async def _refresh_snapshot_if_due(self) -> bool:
        last = self.state.get_sync("snapshot_applied_at")
        if last:
            applied = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - applied < timedelta(
                seconds=self.settings.snapshot_refresh_seconds
            ):
                return False
        assert self.client is not None
        response = await self.client.get("/api/v1/edge-sync/snapshot",
                                         headers=self._headers())
        response.raise_for_status()
        snapshot = response.json()
        if not isinstance(snapshot.get("vehicles"), list) or not isinstance(
            snapshot.get("devices"), list
        ):
            raise TypeError("Snapshot central invalido")
        await asyncio.to_thread(apply_snapshot, self.database, snapshot)
        return True

    async def _flush_outbox(self) -> bool:
        assert self.client is not None
        contacted = False
        while True:
            claimed = await asyncio.to_thread(self.outbox.claim,
                                               self.settings.sync_batch_size)
            if not claimed:
                return contacted
            envelope = {"events": [
                {"event_id": row["aggregate_id"], "event_type": row["event_type"],
                 "schema_version": 1, "payload": row["payload"]}
                for row in claimed
            ]}
            try:
                response = await self.client.post("/api/v1/edge-sync/events",
                                                  json=envelope, headers=self._headers())
                contacted = True
                response.raise_for_status()
                statuses = {item["event_id"]: item["status"]
                            for item in response.json()["results"]}
            except (httpx.HTTPError, TypeError, ValueError, KeyError) as exc:
                for row in claimed:
                    await asyncio.to_thread(self._retry, row, type(exc).__name__)
                raise
            for row in claimed:
                status = statuses.get(row["aggregate_id"], "RETRYABLE_ERROR")
                delay = self._backoff(row["attempts"])
                await asyncio.to_thread(
                    self.outbox.complete, row["id"], status,
                    error=None if status in {"ACCEPTED", "DUPLICATE"} else status,
                    retry_delay_seconds=delay,
                    max_attempts=self.settings.sync_max_attempts,
                )

    async def _flush_media(self) -> bool:
        assert self.client is not None
        contacted = False
        while True:
            rows = await asyncio.to_thread(self.media.claim, self.settings.sync_batch_size)
            if not rows:
                return contacted
            for index, row in enumerate(rows):
                try:
                    content = await asyncio.to_thread(self.media.read_verified, row)
                except (MediaSpoolError, OSError) as exc:
                    await asyncio.to_thread(
                        self.media.complete, row["id"], "PERMANENT_ERROR",
                        error=str(exc), max_attempts=self.settings.sync_max_attempts,
                    )
                    continue
                try:
                    response = await self.client.post(
                        f"/api/v1/edge-sync/media/{row['id']}",
                        data={"media_type": row["media_type"],
                              "scan_id": row["scan_id"] or "",
                              "access_event_id": row["access_event_id"] or "",
                              "checksum_sha256": row["checksum_sha256"],
                              "size_bytes": str(row["size_bytes"]),
                              "schema_version": "1"},
                        files={"file": (f"{row['id']}.webp", content, "image/webp")},
                        headers=self._headers(),
                    )
                    contacted = True
                    response.raise_for_status()
                    status = response.json()["status"]
                except (httpx.HTTPError, TypeError, ValueError, KeyError) as exc:
                    await asyncio.to_thread(
                        self.media.complete, row["id"], "RETRYABLE_ERROR",
                        error=type(exc).__name__, delay_seconds=self._backoff(row["attempts"]),
                        max_attempts=self.settings.sync_max_attempts,
                    )
                    for abandoned in rows[index + 1:]:
                        await asyncio.to_thread(
                            self.media.complete, abandoned["id"], "RETRYABLE_ERROR",
                            error=type(exc).__name__,
                            delay_seconds=self._backoff(abandoned["attempts"]),
                            max_attempts=self.settings.sync_max_attempts,
                        )
                    raise
                await asyncio.to_thread(
                    self.media.complete, row["id"], status,
                    error=None if status in {"ACCEPTED", "DUPLICATE"} else status,
                    delay_seconds=self._backoff(row["attempts"]),
                    max_attempts=self.settings.sync_max_attempts,
                )

    def _retry(self, row: dict[str, Any], error: str) -> None:
        self.outbox.complete(row["id"], "RETRYABLE_ERROR", error=error,
                             retry_delay_seconds=self._backoff(row["attempts"]),
                             max_attempts=self.settings.sync_max_attempts)

    @staticmethod
    def _backoff(attempt: int) -> float:
        base = min(3600.0, float(2 ** min(attempt, 11)))
        return base * random.uniform(0.8, 1.2)

    def status(self) -> dict[str, Any]:
        counts = self.outbox.counts()
        return {"network": "online" if self.online else "offline", "configured": True,
                "last_sync_success_at": self.state.get_sync("last_sync_success_at"),
                "next_sync_attempt_at": (self.next_attempt_at.isoformat()
                                         if self.next_attempt_at else None),
                "sync_error": self.last_error, **counts}
