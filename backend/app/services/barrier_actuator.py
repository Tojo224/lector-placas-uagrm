from __future__ import annotations


async def trigger_barrier_webhook(url: str, direction: str) -> None:
    """Trigger the barrier without making its availability part of access success."""
    from urllib.parse import urlsplit

    import httpx

    parsed = urlsplit(url)
    if (
        parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.path.rstrip("/") == "/api/v1/barrier/trigger"
    ):
        from app.api.v1.barrier import enqueue_barrier_event

        await enqueue_barrier_event(direction=direction)
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                url,
                json={"action": "open", "direction": direction},
                follow_redirects=False,
            )
            response.raise_for_status()
    except httpx.HTTPError:
        pass
