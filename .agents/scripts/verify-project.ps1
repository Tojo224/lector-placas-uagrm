param(
    [string]$Python = "",
    [switch]$SkipVersionCheck
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $backend "app"))) { throw "Backend no encontrado en $backend" }
if (-not (Test-Path (Join-Path $frontend "package.json"))) { throw "Frontend no encontrado o incompleto en $frontend" }
if (-not $Python) {
    $projectPython = Join-Path $backend ".venv\Scripts\python.exe"
    $Python = if (Test-Path $projectPython) { $projectPython } else { "python" }
}
if (Test-Path $Python) { $Python = (Resolve-Path $Python).Path }
$runtime = Join-Path $backend ".runtime"
$matplotlibRuntime = Join-Path $runtime "matplotlib"
New-Item -ItemType Directory -Force -Path $matplotlibRuntime | Out-Null
$env:MPLCONFIGDIR = $matplotlibRuntime

Write-Host "[1/5] Compilando Python"
& $Python -m compileall -q (Join-Path $backend "app") (Join-Path $backend "tests")
if ($LASTEXITCODE -ne 0) { throw "compileall fallo" }

Write-Host "[2/5] Verificando APIs del stack local de vision"
$smoke = @'
import supervision as sv
from fast_alpr import ALPR
from open_image_models.detection.factory import create_detector
from app.services.vehicle_color import HybridVehicleColorAnalyzer
required = {
    "Detections": hasattr(sv, "Detections"),
    "crop_image": hasattr(sv, "crop_image"),
    "ColorLookup.INDEX": hasattr(sv.ColorLookup, "INDEX"),
    "FastALPR": ALPR is not None,
    "create_detector": callable(create_detector),
    "color catalog": len(HybridVehicleColorAnalyzer.DEFAULT_HEX) == 9,
}
missing = [name for name, available in required.items() if not available]
if missing:
    raise SystemExit("APIs faltantes: " + ", ".join(missing))
sv.BoxAnnotator(thickness=2, color_lookup=sv.ColorLookup.INDEX)
sv.LabelAnnotator(text_scale=0.5, color_lookup=sv.ColorLookup.INDEX)
print(f"supervision={sv.__version__}; VISION_APIs=OK")
'@
Push-Location $backend
try { $smoke | & $Python - } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "smoke test de Supervision fallo" }

Write-Host "[3/5] Comprobando dependencias locales"
if ($SkipVersionCheck) {
    Write-Warning "verificacion estricta de versiones omitida por parametro"
} else {
$versions = @'
from importlib import metadata
expected = {
    "supervision": "0.29.1",
    "opencv-python-headless": "4.10.0.84",
    "fast-alpr": "0.4.0",
    "fast-plate-ocr": "1.1.0",
}
errors = []
for package, wanted in expected.items():
    try:
        current = metadata.version(package)
    except metadata.PackageNotFoundError:
        errors.append(f"{package}: no instalado")
        continue
    print(f"{package}={current}")
    if current != wanted:
        errors.append(f"{package}: esperado {wanted}, actual {current}")
for required in ("numpy", "httpx", "onnxruntime", "open-image-models", "tokenizers", "huggingface-hub"):
    try:
        print(f"{required}={metadata.version(required)}")
    except metadata.PackageNotFoundError:
        errors.append(f"{required}: no instalado")
if errors:
    raise SystemExit("Dependencias incompatibles: " + "; ".join(errors))
'@
$versions | & $Python -
if ($LASTEXITCODE -ne 0) { throw "las dependencias instaladas no coinciden con la arquitectura OCR" }
}

Write-Host "[4/5] Ejecutando pytest del backend"
Push-Location $backend
try {
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "pytest del backend fallo" }
} finally { Pop-Location }

Write-Host "[5/5] Construyendo frontend"
Push-Location $frontend
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "build frontend fallo" }
} finally { Pop-Location }

Write-Host "Verificacion completada correctamente"
