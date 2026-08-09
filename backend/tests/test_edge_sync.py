from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import cv2
import httpx
import numpy as np
import pytest
from app.services.plate_analysis import analyze_plate_bytes
from edge_agent.cache import apply_snapshot
from edge_agent.config import EdgeSettings
from edge_agent.db import EdgeDatabase
from edge_agent.db.repositories import OutboxRepository
from edge_agent.sync import SyncWorker


def snapshot(version="v1", plate="1234ABC"):
    now = datetime.now(timezone.utc).isoformat()
    return {"version": version, "generated_at": now,
            "vehicles": [{"central_id": "vehicle-1", "plate": plate,
                          "is_active": True}],
            "devices": [{"central_id": "device-1", "name": "Porton",
                         "location": "Campus", "direction": "AUTO",
                         "is_active": True}]}


def settings(tmp_path, **overrides):
    values = {"data_dir": tmp_path, "central_url": "https://central.test",
              "device_id": "device-1", "device_key": "edge-only-key",
              "snapshot_refresh_seconds": 0, "sync_batch_size": 25,
              "sync_max_attempts": 5}
    values.update(overrides)
    return EdgeSettings(**values)


def database(tmp_path):
    db = EdgeDatabase(tmp_path / "edge.sqlite3")
    db.initialize()
    return db


def client(handler):
    return httpx.AsyncClient(base_url="https://central.test",
                             transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_initial_provision_and_snapshot_renewal_are_atomic(tmp_path):
    db = database(tmp_path)
    current = {"value": snapshot("v1")}

    def handler(request):
        assert request.headers["x-edge-device-id"] == "device-1"
        assert request.headers["authorization"] == "Bearer edge-only-key"
        if request.url.path.endswith("snapshot"):
            return httpx.Response(200, json=current["value"])
        return httpx.Response(200, json={"results": []})

    async with client(handler) as http:
        worker = SyncWorker(db, settings(tmp_path), http)
        await worker.run_once()
        current["value"] = snapshot("v2", "5678DEF")
        await worker.run_once()
    with db.connection() as connection:
        assert connection.execute("SELECT plate FROM cached_vehicles").fetchone()[0] == "5678DEF"
        assert connection.execute(
            "SELECT value FROM sync_state WHERE key='snapshot_version'"
        ).fetchone()[0] == "v2"


@pytest.mark.anyio
async def test_failed_or_invalid_refresh_preserves_previous_snapshot(tmp_path):
    db = database(tmp_path)
    apply_snapshot(db, snapshot("good"))

    def handler(_request):
        return httpx.Response(200, json={"version": "broken", "vehicles": "bad"})

    async with client(handler) as http:
        worker = SyncWorker(db, settings(tmp_path), http)
        await worker.run_once()
    assert worker.online is False
    with db.connection() as connection:
        assert connection.execute("SELECT plate FROM cached_vehicles").fetchone()[0] == "1234ABC"


def enqueue_many(db, total):
    repo = OutboxRepository(db)
    ids = []
    for index in range(total):
        event_id = f"00000000-0000-4000-8000-{index:012d}"
        repo.enqueue(event_type="SCAN_RECORDED", aggregate_type="scan",
                     aggregate_id=event_id,
                     payload={"scan_id": event_id, "plate": "1234ABC",
                              "captured_at": datetime.now(timezone.utc).isoformat()})
        ids.append(event_id)
    return ids


@pytest.mark.anyio
async def test_batches_drain_hundreds_and_duplicate_is_success(tmp_path):
    db = database(tmp_path)
    apply_snapshot(db, snapshot())
    sent = []
    enqueue_many(db, 350)

    def handler(request):
        if request.url.path.endswith("snapshot"):
            return httpx.Response(200, json=snapshot())
        events = json.loads(request.content)["events"]
        sent.extend(item["event_id"] for item in events)
        return httpx.Response(200, json={"results": [
            {"event_id": item["event_id"],
             "status": "DUPLICATE" if item["event_id"] == sent[0] else "ACCEPTED"}
            for item in events]})

    async with client(handler) as http:
        worker = SyncWorker(db, settings(tmp_path), http)
        await worker.run_once()
    assert len(sent) == 350
    assert OutboxRepository(db).counts()["synced"] == 350


@pytest.mark.anyio
async def test_timeout_after_server_acceptance_retries_same_event_id(tmp_path):
    db = database(tmp_path)
    apply_snapshot(db, snapshot())
    event_id = enqueue_many(db, 1)[0]
    accepted = set()
    calls = 0

    def handler(request):
        nonlocal calls
        if request.url.path.endswith("snapshot"):
            return httpx.Response(200, json=snapshot())
        calls += 1
        item = json.loads(request.content)["events"][0]
        if calls == 1:
            accepted.add(item["event_id"])
            raise httpx.ReadTimeout("lost response", request=request)
        return httpx.Response(200, json={"results": [
            {"event_id": item["event_id"], "status": "DUPLICATE"}]})

    async with client(handler) as http:
        worker = SyncWorker(db, settings(tmp_path), http)
        await worker.run_once()
        with db.transaction() as connection:
            connection.execute("UPDATE outbox SET next_attempt_at=NULL")
        await worker.run_once()
    assert accepted == {event_id}
    assert calls == 2
    assert OutboxRepository(db).counts()["synced"] == 1


def test_restart_recovers_in_flight_and_retry_dead_letter(tmp_path):
    db = database(tmp_path)
    repo = OutboxRepository(db)
    enqueue_many(db, 2)
    claimed = repo.claim(2)
    assert len(claimed) == 2
    assert repo.recover_abandoned() == 2
    reclaimed = repo.claim(2)
    repo.complete(reclaimed[0]["id"], "RETRYABLE_ERROR", retry_delay_seconds=8)
    repo.complete(reclaimed[1]["id"], "PERMANENT_ERROR")
    with db.connection() as connection:
        retry = connection.execute(
            "SELECT attempts,next_attempt_at FROM outbox WHERE status='RETRY'"
        ).fetchone()
    assert retry["attempts"] == 2
    assert retry["next_attempt_at"] is not None
    assert repo.counts()["dead_letters"] == 1


def test_retry_backoff_is_exponential(monkeypatch):
    monkeypatch.setattr("edge_agent.sync.random.uniform", lambda _a, _b: 1.0)
    assert [SyncWorker._backoff(attempt) for attempt in range(1, 5)] == [2, 4, 8, 16]


@pytest.mark.anyio
async def test_ocr_remains_responsive_while_sync_is_slow(tmp_path):
    db = database(tmp_path)
    apply_snapshot(db, snapshot())
    enqueue_many(db, 1)

    async def handler(request):
        if request.url.path.endswith("events"):
            await asyncio.sleep(0.2)
            item = json.loads(request.content)["events"][0]
            return httpx.Response(200, json={"results": [
                {"event_id": item["event_id"], "status": "ACCEPTED"}]})
        return httpx.Response(200, json=snapshot())

    class Engine:
        def predict(self, _image):
            return []

    ok, encoded = cv2.imencode(".jpg", np.zeros((32, 64, 3), dtype=np.uint8))
    assert ok
    async with client(handler) as http:
        worker = SyncWorker(db, settings(tmp_path), http)
        sync_task = asyncio.create_task(worker.run_once())
        result, _elapsed = await asyncio.wait_for(
            analyze_plate_bytes(encoded.tobytes(), True, Engine(),
                                settings(tmp_path).pipeline_config()),
            timeout=0.15,
        )
        await sync_task
    assert result["status"] == "LOW_CONFIDENCE"


def test_edge_database_contains_no_device_or_cloud_credentials(tmp_path):
    db = database(tmp_path)
    with db.connection() as connection:
        ddl = " ".join(row[0] or "" for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table'"
        )).lower()
    assert "edge_device_key" not in ddl
    assert "cloudinary" not in ddl
    assert "admin_password" not in ddl
