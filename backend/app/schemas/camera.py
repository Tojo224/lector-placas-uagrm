from __future__ import annotations

from pydantic import BaseModel


class CameraStatus(BaseModel):
    alive: bool
    pid: int | None = None
    start_count: int = 0
