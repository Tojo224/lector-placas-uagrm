"""
POR-001: Centralización de rutas del sistema de archivos.
Todas las rutas de directorios de runtime, uploads y caché deben
importarse desde aquí en lugar de calcularse de forma dispersa.
"""
from __future__ import annotations

from pathlib import Path

# Raíz del proyecto: lector-placas-uagrm/backend/
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# Directorio de runtime (nunca rastrear en git)
RUNTIME_DIR: Path = PROJECT_ROOT / ".runtime"

# Directorio para los modelos de PaddleOCR (det, rec, cls)
OCR_MODEL_DIR: Path = RUNTIME_DIR / "paddleocr"

# Directorio de caché de Matplotlib (evita escrituras en HOME)
MPLCONFIG_DIR: Path = RUNTIME_DIR / "matplotlib"

# Directorio de uploads de imágenes de placas y vehículos
UPLOADS_DIR: Path = PROJECT_ROOT / "uploads"

# Directorio de caché para Hugging Face
HF_CACHE_DIR: Path = RUNTIME_DIR / "huggingface"

import os
os.environ["HF_HOME"] = str(HF_CACHE_DIR)

# Asegurarse de que existan al importar este módulo
for _dir in (RUNTIME_DIR, OCR_MODEL_DIR, MPLCONFIG_DIR, UPLOADS_DIR, HF_CACHE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
