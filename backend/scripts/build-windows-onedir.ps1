param(
    [string]$Python = "",
    [string]$DistPath = ""
)

$ErrorActionPreference = "Stop"
$backend = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$root = (Resolve-Path (Join-Path $backend "..")).Path
if (-not $Python) { $Python = Join-Path $backend ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "Python de build no encontrado: $Python" }
if (-not $DistPath) { $DistPath = Join-Path $backend "dist\windows" }

Push-Location (Join-Path $root "frontend")
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "El build de React fallo" }
} finally { Pop-Location }

$manifestPath = Join-Path $backend "packaging\models.json"
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$modelStage = Join-Path $backend ".runtime\windows-package-models"
if (Test-Path $modelStage) {
    Remove-Item -LiteralPath $modelStage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $modelStage | Out-Null
foreach ($model in $manifest.models) {
    if ($model.source.StartsWith("repo:")) {
        $source = Join-Path $root $model.source.Substring(5)
    } else {
        $source = Join-Path $env:USERPROFILE $model.source
    }
    if (-not (Test-Path $source -PathType Leaf)) {
        throw "Falta el modelo requerido en el host de build: $source"
    }
    $actualHash = (Get-FileHash $source -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $model.sha256) {
        throw "Checksum inesperado para $($model.name): $actualHash"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $modelStage $model.name) -Force
}
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $modelStage "models.json") -Force

$env:EDGE_PACKAGE_MODEL_DIR = $modelStage
$workPath = Join-Path $backend ".runtime\pyinstaller"
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistPath `
    --workpath $workPath `
    (Join-Path $backend "packaging\UAGRMPlateAgent.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo" }

$exe = Join-Path $DistPath "UAGRMPlateAgent\UAGRMPlateAgent.exe"
if (-not (Test-Path $exe -PathType Leaf)) { throw "No se genero $exe" }
$size = (Get-ChildItem (Split-Path $exe) -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host "Distribucion creada: $exe"
Write-Host ("Tamano onedir: {0:N1} MiB" -f ($size / 1MB))
