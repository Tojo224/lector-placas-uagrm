param(
    [string]$Exe = "C:\Program Files\UAGRM\PlateAgent\UAGRMPlateAgent.exe",
    [int]$Port = 18765,
    [string]$DataDir = "",
    [string]$ImagePath = ""
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
if (-not $DataDir) {
    $DataDir = Join-Path $env:TEMP ("UAGRMPlateAgent-benchmark-" + [guid]::NewGuid())
}
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$oldData = $env:EDGE_DATA_DIR
$oldPort = $env:EDGE_PORT
$oldCentral = $env:EDGE_CENTRAL_URL
$env:EDGE_DATA_DIR = $DataDir
$env:EDGE_PORT = "$Port"
Remove-Item Env:EDGE_CENTRAL_URL -ErrorAction SilentlyContinue

$client = [Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromMilliseconds(500)
$watch = [Diagnostics.Stopwatch]::StartNew()
$process = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe) -PassThru
$apiMs = $null
$reactMs = $null
$initializingMs = $null
$readyMs = $null
$peakWorkingSet = 0L
$health = $null

function Try-GetJson([string]$Url) {
    try {
        $response = $client.GetAsync($Url).GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) { return $null }
        return ($response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json)
    } catch { return $null }
}

function Post-Image([bool]$Confirm) {
    if ($ImagePath) { $png = [IO.File]::ReadAllBytes((Resolve-Path $ImagePath)) }
    else { $png = [Convert]::FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=") }
    $content = [Net.Http.ByteArrayContent]::new($png)
    $content.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::Parse("image/png")
    $form = [Net.Http.MultipartFormDataContent]::new()
    $form.Add($content, "file", "benchmark.png")
    $requestWatch = [Diagnostics.Stopwatch]::StartNew()
    $response = $client.PostAsync(
        "http://127.0.0.1:$Port/api/v1/edge/analyze?realtime=true&confirm=$($Confirm.ToString().ToLowerInvariant())",
        $form
    ).GetAwaiter().GetResult()
    $requestWatch.Stop()
    if (-not $response.IsSuccessStatusCode) {
        throw "Analyze fallo con HTTP $([int]$response.StatusCode)"
    }
    $form.Dispose()
    return [math]::Round($requestWatch.Elapsed.TotalMilliseconds, 1)
}

try {
    while ($watch.Elapsed.TotalSeconds -lt 120 -and -not $readyMs) {
        if ($process.HasExited) { throw "El agente termino con codigo $($process.ExitCode)" }
        $process.Refresh()
        $peakWorkingSet = [math]::Max($peakWorkingSet, $process.WorkingSet64)
        $candidate = Try-GetJson "http://127.0.0.1:$Port/api/v1/edge/health"
        if ($candidate) {
            if ($null -eq $apiMs) { $apiMs = $watch.Elapsed.TotalMilliseconds }
            $health = $candidate
            if ($candidate.lifecycle_state -eq "INITIALIZING_OCR" -and $null -eq $initializingMs) {
                $initializingMs = $watch.Elapsed.TotalMilliseconds
            }
            if ($null -eq $reactMs) {
                try {
                    $reactResponse = $client.GetAsync("http://127.0.0.1:$Port/subir-placa").GetAwaiter().GetResult()
                    if ($reactResponse.IsSuccessStatusCode) { $reactMs = $watch.Elapsed.TotalMilliseconds }
                } catch {}
            }
            if ($candidate.ocr_ready) { $readyMs = $watch.Elapsed.TotalMilliseconds }
        }
        Start-Sleep -Milliseconds 50
    }
    if ($null -eq $readyMs) { throw "OCR no quedo listo en 120 segundos" }
    $first = Post-Image $false
    $warm = @(1..5 | ForEach-Object { Post-Image $false })
    $confirmed = Post-Image $true
    $process.Refresh()
    $result = [ordered]@{
        api_available_ms = [math]::Round($apiMs, 1)
        react_available_ms = [math]::Round($reactMs, 1)
        initializing_ocr_ms = if ($null -eq $initializingMs) { $null } else { [math]::Round($initializingMs, 1) }
        ocr_ready_ms = [math]::Round($readyMs, 1)
        first_inference_ms = $first
        warm_inference_avg_ms = [math]::Round(($warm | Measure-Object -Average).Average, 1)
        warm_inference_min_ms = [math]::Round(($warm | Measure-Object -Minimum).Minimum, 1)
        confirmed_total_ms = $confirmed
        working_set_mb = [math]::Round($process.WorkingSet64 / 1MB, 1)
        peak_working_set_mb = [math]::Round($peakWorkingSet / 1MB, 1)
        cpu_seconds = [math]::Round($process.CPU, 2)
        startup_timings = $health.startup_timings
        data_dir = $DataDir
    }
    $result | ConvertTo-Json -Depth 5
} finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id }
    $client.Dispose()
    $env:EDGE_DATA_DIR = $oldData
    $env:EDGE_PORT = $oldPort
    if ($null -eq $oldCentral) { Remove-Item Env:EDGE_CENTRAL_URL -ErrorAction SilentlyContinue }
    else { $env:EDGE_CENTRAL_URL = $oldCentral }
}
