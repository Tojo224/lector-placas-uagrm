from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OCRPipelineConfig:
    confidence_threshold: float = 0.55
    roi_x: int | None = None
    roi_y: int | None = None
    roi_width: int | None = None
    roi_height: int | None = None
    use_supervision_annotations: bool = True
