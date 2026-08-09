"""Local-only OCR process for the UAGRM plate reader."""

import os
from pathlib import Path

_RUNTIME_DIR = Path(__file__).resolve().parents[1] / ".runtime" / "edge"
_MPLCONFIG_DIR = _RUNTIME_DIR / "matplotlib"
_MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIG_DIR))

__version__ = "0.1.0"
