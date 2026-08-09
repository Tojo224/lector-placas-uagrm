from __future__ import annotations

import os
from typing import Any

from edge_agent.config import EdgeSettings

# Never let the edge startup download models implicitly. Production packaging
# will bundle the same model artifacts; development requires a populated cache.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def create_ocr_engine(settings: EdgeSettings) -> Any:
    from fast_alpr import ALPR

    providers = [settings.execution_provider]
    return ALPR(
        detector_model=settings.detector_model,
        detector_conf_thresh=settings.detector_confidence,
        detector_providers=providers,
        ocr_model=settings.ocr_model,
        ocr_device="cpu",
        ocr_providers=providers,
    )
