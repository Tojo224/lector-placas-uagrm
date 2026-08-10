param(
    [string]$Python = "",
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$backend = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$root = (Resolve-Path (Join-Path $backend "..")).Path
if (-not $Python) { $Python = Join-Path $backend ".venv\Scripts\python.exe" }
$versionOutput = $null
Push-Location $backend
try {
    $versionOutput = & $Python -c "from edge_agent.version import PRODUCT_VERSION; print(PRODUCT_VERSION)"
} finally { Pop-Location }
$version = if ($versionOutput) { $versionOutput.Trim() } else { "" }
if ($LASTEXITCODE -ne 0 -or -not $version) { throw "No se pudo resolver la version" }

$versionFile = Join-Path $backend ".runtime\UAGRMPlateAgent-version.txt"
$versionTuple = (($version.Split('.') + @('0','0','0','0'))[0..3] -join ', ')
@"
VSVersionInfo(ffi=FixedFileInfo(filevers=($versionTuple), prodvers=($versionTuple),
mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName', 'Universidad Autonoma Gabriel Rene Moreno'), StringStruct('FileDescription', 'UAGRM Plate Agent'), StringStruct('FileVersion', '$version'), StringStruct('InternalName', 'UAGRMPlateAgent'), StringStruct('OriginalFilename', 'UAGRMPlateAgent.exe'), StringStruct('ProductName', 'UAGRM Plate Agent'), StringStruct('ProductVersion', '$version')])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"@ | Set-Content -LiteralPath $versionFile -Encoding UTF8
$env:EDGE_VERSION_FILE = $versionFile

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build-windows-onedir.ps1") -Python $Python
if ($LASTEXITCODE -ne 0) { throw "El build onedir fallo" }

if (-not $InnoCompiler) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $InnoCompiler = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $InnoCompiler -or -not (Test-Path $InnoCompiler)) {
    throw "Inno Setup 6 no esta instalado o no se encontro ISCC.exe"
}

& $InnoCompiler "/DMyAppVersion=$version" (Join-Path $backend "packaging\UAGRMPlateAgent.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup fallo" }

$dist = Join-Path $backend "dist\windows"
$setup = Join-Path $dist "UAGRMPlateAgent-Setup.exe"
$onedirExe = Join-Path $dist "UAGRMPlateAgent\UAGRMPlateAgent.exe"
if (-not (Test-Path $setup)) { throw "No se genero $setup" }
$checksums = @($setup, $onedirExe) | ForEach-Object {
    $hash = Get-FileHash $_ -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($_))"
}
$checksums | Set-Content (Join-Path $dist "SHA256SUMS.txt") -Encoding ASCII
Write-Host "Instalador creado: $setup"
Write-Host "Version: $version"
