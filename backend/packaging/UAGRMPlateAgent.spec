from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs


spec_dir = Path(SPECPATH)
backend_dir = spec_dir.parent
repo_dir = backend_dir.parent
model_dir = Path(os.environ["EDGE_PACKAGE_MODEL_DIR"])
frontend_dir = repo_dir / "frontend" / "dist"

if not (frontend_dir / "index.html").is_file():
    raise SystemExit("frontend/dist no existe; ejecute npm run build antes de empaquetar")

datas = [
    (str(frontend_dir), "frontend/dist"),
    (str(model_dir), "resources/models"),
]
binaries = []
hiddenimports = [
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

for package in ("fast_alpr", "fast_plate_ocr", "open_image_models"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

binaries += collect_dynamic_libs("onnxruntime")

a = Analysis(
    [str(backend_dir / "edge_agent" / "windows_entry.py")],
    pathex=[str(backend_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "alembic",
        "cloudinary",
        "psycopg",
        "sqlalchemy",
        "scipy",
        "supervision",
        "matplotlib",
        "app.services.clip_color",
        "app.services.vehicle_color",
        "app.services.vehicle_detection",
        "app.services.vehicle_type",
        "tokenizers",
        "transformers",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UAGRMPlateAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    version=os.environ.get("EDGE_VERSION_FILE"),
    disable_windowed_traceback=False,
    contents_directory="runtime",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="UAGRMPlateAgent",
)
