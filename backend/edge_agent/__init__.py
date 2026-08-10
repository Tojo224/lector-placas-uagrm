"""Local-only OCR process for the UAGRM plate reader."""

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _DATA_ROOT = Path(
        os.getenv("EDGE_DATA_DIR")
        or Path(os.getenv("PROGRAMDATA", Path.home())) / "UAGRM" / "PlateAgent"
    )
    _RUNTIME_DIR = _DATA_ROOT / "runtime"
else:
    _RUNTIME_DIR = Path(__file__).resolve().parents[1] / ".runtime" / "edge"
_MPLCONFIG_DIR = _RUNTIME_DIR / "matplotlib"
_MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIG_DIR))

from edge_agent.version import PRODUCT_VERSION as __version__
