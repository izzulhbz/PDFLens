# Windows version of pull_models.sh: downloads the Ollama models PDFLens needs
# into the ollama container's volume. Run from the repository root while the
# stack is up:
#   docker compose up -d ollama
#   .\scripts\pull_models.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Read one value from .env, without loading the whole file into the session.
function Read-EnvValue([string]$Name) {
    if (Test-Path ".env") {
        $line = Get-Content ".env" | Where-Object { $_ -match "^$Name=" } | Select-Object -Last 1
        if ($line) { return ($line -split "=", 2)[1].Trim() }
    }
    return $null
}

$embedModel = if ($env:OLLAMA_EMBED_MODEL) { $env:OLLAMA_EMBED_MODEL } else { Read-EnvValue "OLLAMA_EMBED_MODEL" }
$chatModel = if ($env:OLLAMA_CHAT_MODEL) { $env:OLLAMA_CHAT_MODEL } else { Read-EnvValue "OLLAMA_CHAT_MODEL" }
if (-not $embedModel) { $embedModel = "nomic-embed-text" }
if (-not $chatModel) { $chatModel = "llama3.2" }

foreach ($model in @($embedModel, $chatModel)) {
    Write-Host "Pulling $model ..."
    docker compose exec -T ollama ollama pull $model
    if ($LASTEXITCODE -ne 0) { throw "Failed to pull $model" }
}

Write-Host ""
docker compose exec -T ollama ollama list
