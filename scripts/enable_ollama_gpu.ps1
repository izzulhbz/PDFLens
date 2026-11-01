# Sets up the optional "Ollama GPU" provider on Windows.
#
# PDFLens's Docker Ollama runs on the CPU only. Ollama installed natively on
# Windows can use the GPU, including an integrated one such as Intel Arc
# (through Vulkan), but it skips integrated GPUs unless OLLAMA_IGPU_ENABLE=1.
#
# This script:
#   1. sets OLLAMA_IGPU_ENABLE=1 for your Windows user (persistent),
#   2. restarts the Ollama app so it picks the setting up,
#   3. pulls the model if it's missing,
#   4. loads it once and reports whether it landed on the GPU.
#
# Run from the repo root:  .\scripts\enable_ollama_gpu.ps1
# Undo: [Environment]::SetEnvironmentVariable("OLLAMA_IGPU_ENABLE", $null, "User"),
# then restart Ollama.

param(
    [string]$Model = "qwen2.5:7b",
    [string]$Url = "http://127.0.0.1:11434"
)

$ErrorActionPreference = "Stop"
$app = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
$cli = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
if (-not (Test-Path $cli)) {
    throw "Ollama for Windows isn't installed (expected $cli). Get it from https://ollama.com/download."
}

Write-Host "1/4 Setting OLLAMA_IGPU_ENABLE=1 for your user..."
[Environment]::SetEnvironmentVariable("OLLAMA_IGPU_ENABLE", "1", "User")

Write-Host "2/4 Restarting Ollama..."
Get-Process -Name "ollama app", "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
# Started from this session, so it inherits the new variable even before
# Windows hands it to newly launched programs.
$env:OLLAMA_IGPU_ENABLE = "1"
Start-Process -FilePath $app
$ready = $false
foreach ($i in 1..30) {
    try { Invoke-RestMethod "$Url/api/version" | Out-Null; $ready = $true; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw "Ollama didn't come back on $Url." }

Write-Host "3/4 Checking for $Model..."
$names = (Invoke-RestMethod "$Url/api/tags").models.name
if ($names -notcontains $Model) {
    Write-Host "    Pulling $Model (several GB, only once)..."
    & $cli pull $Model
}

Write-Host "4/4 Loading $Model to see where it runs..."
$body = @{ model = $Model; prompt = "Say OK."; stream = $false } | ConvertTo-Json
Invoke-RestMethod "$Url/api/generate" -Method Post -Body $body -ContentType "application/json" | Out-Null
$loaded = (Invoke-RestMethod "$Url/api/ps").models | Where-Object { $_.name -eq $Model }
$gb = [math]::Round($loaded.size_vram / 1GB, 1)
if ($loaded.size_vram -gt 0) {
    Write-Host "OK: $Model is on the GPU ($gb GB)." -ForegroundColor Green
} else {
    Write-Host "Ollama is running $Model on the CPU: no usable GPU was found." -ForegroundColor Yellow
    Write-Host "Check the log: $env:LOCALAPPDATA\Ollama\server.log (search for 'inference compute')."
}

Write-Host ""
Write-Host "Then add these to .env and run: docker compose up -d backend"
Write-Host "  OLLAMA_GPU_BASE_URL=$Url"
Write-Host "  OLLAMA_GPU_DOCKER_URL=$($Url -replace '127.0.0.1|localhost', 'host.docker.internal')"
