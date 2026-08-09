from __future__ import annotations

from datetime import datetime, timedelta, timezone


def is_duplicate_access(
    last_access_at: datetime | None,
    now_utc: datetime,
    cooldown_seconds: float,
) -> bool:
    if last_access_at is None:
        return False
    if last_access_at.tzinfo is None:
        last_access_at = last_access_at.replace(tzinfo=timezone.utc)
    return now_utc - last_access_at < timedelta(seconds=cooldown_seconds)


def infer_access_type(
    device_name: str | None,
    campus_state: object | None,
) -> str:
    normalized_name = (device_name or "").lower()
    if "entrada" in normalized_name or "ingreso" in normalized_name:
        return "ENTRADA"
    if "salida" in normalized_name or "egreso" in normalized_name:
        return "SALIDA"
    state_value = getattr(campus_state, "value", campus_state)
    if state_value == "DENTRO":
        return "SALIDA"
    return "ENTRADA"
