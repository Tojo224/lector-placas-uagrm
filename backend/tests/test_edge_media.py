from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

import cv2
import httpx
import numpy as np
import pytest
from app.services.image_processing import ImageProcessingError
from edge_agent.cache import apply_snapshot
from edge_agent.config import EdgeSettings
from edge_agent.db import EdgeDatabase
from edge_agent.media_spool import MediaSpool, MediaSpoolError
from edge_agent.offline_access import OfflineAccessService
from edge_agent.sync import SyncWorker


def image_bytes() -> bytes:
    ok, encoded = cv2.imencode(".jpg", np.full((80, 160, 3), 170, dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def setup(tmp_path):
    config = EdgeSettings(data_dir=tmp_path, central_url="https://central.test",
                          device_id="device-1", device_key="key",
                          snapshot_refresh_seconds=3600, sync_batch_size=25)
    db = EdgeDatabase(config.database_path())
    db.initialize()
    now = datetime.now(timezone.utc).isoformat()
    apply_snapshot(db, {"version": "v1", "generated_at": now,
        "vehicles": [{"central_id": "vehicle-1", "plate": "1234ABC", "is_active": True}],
        "devices": [{"central_id": "device-1", "name": "Porton", "location": "Campus",
                     "direction": "AUTO", "is_active": True}]})
    outcome = OfflineAccessService(db, 24, 0).process(
        {"status": "DETECTED", "detected_plate": "1234ABC",
         "normalized_plate": "1234ABC", "combined_confidence": 0.95}, True,
        "device-1")
    return db, config, outcome


def media_row(db, media_id):
    with db.connection() as connection:
        return dict(connection.execute(
            "SELECT * FROM local_media WHERE id=?", (media_id,)
        ).fetchone())


def test_evidence_is_webp_atomic_durable_and_survives_restart(tmp_path):
    db, config, outcome = setup(tmp_path)
    spool = MediaSpool(db, config)
    media_id = spool.capture(image_bytes(), outcome)
    row = media_row(db, media_id)
    path = config.media_spool_dir() / row["relative_path"]
    assert path.suffix == ".webp" and path.is_file()
    assert not list(path.parent.glob("*.tmp"))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["checksum_sha256"]
    restarted = EdgeDatabase(config.database_path())
    restarted.initialize()
    assert MediaSpool(restarted, config).claim(1)[0]["id"] == media_id


def test_missing_corrupt_checksum_and_traversal_are_rejected(tmp_path):
    db, config, outcome = setup(tmp_path)
    spool = MediaSpool(db, config)
    missing = spool.capture(image_bytes(), outcome)
    row = media_row(db, missing)
    (spool.root / row["relative_path"]).unlink()
    with pytest.raises(MediaSpoolError, match="faltante"):
        spool.read_verified(row)

    corrupt = spool.capture(image_bytes(), outcome)
    row = media_row(db, corrupt)
    path = spool.root / row["relative_path"]
    path.write_bytes(b"corrupt")
    row["size_bytes"] = len(b"corrupt")
    with pytest.raises(MediaSpoolError, match="Checksum"):
        spool.read_verified(row)

    row["relative_path"] = "../outside.webp"
    with pytest.raises(MediaSpoolError, match="insegura"):
        spool.read_verified(row)


def test_size_limit_and_low_disk_fail_without_partial_metadata(tmp_path, monkeypatch):
    db, config, outcome = setup(tmp_path)
    limited = EdgeSettings(**{**config.__dict__, "media_max_upload_bytes": 10})
    with pytest.raises(ImageProcessingError, match="tamano"):
        MediaSpool(db, limited).capture(image_bytes(), outcome)
    monkeypatch.setattr("edge_agent.media_spool.shutil.disk_usage",
                        lambda _path: type("Usage", (), {"free": 1, "total": 10})())
    with pytest.raises(MediaSpoolError, match="Espacio"):
        MediaSpool(db, config).capture(image_bytes(), outcome)
    with db.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_media").fetchone()[0] == 0


@pytest.mark.anyio
async def test_reconnect_upload_timeout_duplicate_and_cloud_failure(tmp_path):
    db, config, outcome = setup(tmp_path)
    spool = MediaSpool(db, config)
    media_id = spool.capture(image_bytes(), outcome)
    calls = 0

    def handler(request):
        nonlocal calls
        if request.url.path.endswith("events"):
            events = __import__("json").loads(request.content)["events"]
            return httpx.Response(200, json={"results": [
                {"event_id": item["event_id"], "status": "ACCEPTED"} for item in events]})
        if "/media/" in request.url.path:
            calls += 1
            if calls == 1:
                raise httpx.ReadTimeout("respuesta perdida", request=request)
            if calls == 2:
                return httpx.Response(200, json={"media_id": media_id,
                                                 "status": "DUPLICATE"})
            return httpx.Response(200, json={"media_id": media_id,
                                             "status": "RETRYABLE_ERROR"})
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(base_url="https://central.test",
                                 transport=httpx.MockTransport(handler)) as client:
        worker = SyncWorker(db, config, client)
        await worker.run_once()
        assert media_row(db, media_id)["status"] == "RETRY"
        with db.transaction() as connection:
            connection.execute("UPDATE local_media SET next_attempt_at=NULL")
            connection.execute("UPDATE outbox SET next_attempt_at=NULL")
        await worker.run_once()
    assert media_row(db, media_id)["status"] == "SYNCED"
    assert (spool.root / media_row(db, media_id)["relative_path"]).exists()


@pytest.mark.anyio
async def test_cloudinary_failure_reported_by_central_keeps_media_for_retry(tmp_path):
    db, config, outcome = setup(tmp_path)
    media_id = MediaSpool(db, config).capture(image_bytes(), outcome)

    def handler(request):
        if request.url.path.endswith("events"):
            events = __import__("json").loads(request.content)["events"]
            return httpx.Response(200, json={"results": [
                {"event_id": item["event_id"], "status": "ACCEPTED"} for item in events]})
        return httpx.Response(200, json={"media_id": media_id,
                                         "status": "RETRYABLE_ERROR"})

    async with httpx.AsyncClient(base_url="https://central.test",
                                 transport=httpx.MockTransport(handler)) as client:
        await SyncWorker(db, config, client).run_once()
    row = media_row(db, media_id)
    assert row["status"] == "RETRY"
    assert (config.media_spool_dir() / row["relative_path"]).exists()


@pytest.mark.anyio
async def test_backend_unavailable_keeps_media_for_retry(tmp_path):
    db, config, outcome = setup(tmp_path)
    media_id = MediaSpool(db, config).capture(image_bytes(), outcome)

    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(base_url="https://central.test",
                                 transport=httpx.MockTransport(handler)) as client:
        worker = SyncWorker(db, config, client)
        await worker.run_once()
    assert worker.online is False
    assert media_row(db, media_id)["status"] == "RETRY"


def test_restart_recovers_media_in_flight(tmp_path):
    db, config, outcome = setup(tmp_path)
    spool = MediaSpool(db, config)
    media_id = spool.capture(image_bytes(), outcome)
    assert spool.claim(1)[0]["id"] == media_id
    restarted = MediaSpool(EdgeDatabase(config.database_path()), config)
    assert restarted.recover_abandoned() == 1
    assert restarted.claim(1)[0]["id"] == media_id


def test_several_hundred_evidences_remain_durable(tmp_path):
    db, config, outcome = setup(tmp_path)
    spool = MediaSpool(db, config)
    content = image_bytes()
    for _ in range(250):
        assert spool.capture(content, outcome)
    assert spool.stats()["pending"] == 250
    assert len(spool.claim(300)) == 250


@pytest.mark.anyio
async def test_slow_media_upload_does_not_block_local_work(tmp_path):
    db, config, outcome = setup(tmp_path)
    MediaSpool(db, config).capture(image_bytes(), outcome)

    async def handler(request):
        if request.url.path.endswith("events"):
            events = __import__("json").loads(request.content)["events"]
            return httpx.Response(200, json={"results": [
                {"event_id": item["event_id"], "status": "ACCEPTED"} for item in events]})
        await asyncio.sleep(0.2)
        return httpx.Response(200, json={"status": "ACCEPTED"})

    async with httpx.AsyncClient(base_url="https://central.test",
                                 transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(SyncWorker(db, config, client).run_once())
        local = await asyncio.wait_for(asyncio.to_thread(
            OfflineAccessService(db, 24, 0).process,
            {"status": "DETECTED", "detected_plate": "1234ABC",
             "normalized_plate": "1234ABC", "combined_confidence": 0.95},
            True, "device-1"), timeout=0.15)
        await task
    assert local["decision"] == "ALLOW"
