<#
.SYNOPSIS
  Start Agent Skills Dev Studio.

.DESCRIPTION
  Prod mode (default): builds the React SPA and serves it plus the API from
  uvicorn on http://127.0.0.1:8000. Dev mode (-Dev): runs uvicorn and the Vite
  dev server (http://127.0.0.1:5173) with hot reload and an /api proxy.

.NOTES
  Requires .env (copy from .env.example) and an `az login` whose identity holds
  the Cognitive Services OpenAI User role. Auth is managed identity only.
#>
param([switch]$Dev)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Warning 'Created .env from .env.example - fill in AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_MODEL, then re-run.'
    exit 1
}

uv sync

if ($Dev) {
    Push-Location 'frontend'; npm install; Pop-Location
    Start-Process pwsh -ArgumentList '-NoExit', '-Command', "cd '$root'; uv run uvicorn backend.main:app --reload"
    Start-Process pwsh -ArgumentList '-NoExit', '-Command', "cd '$root/frontend'; npm run dev"
    Write-Host 'Dev: API http://127.0.0.1:8000  UI http://127.0.0.1:5173'
} else {
    Push-Location 'frontend'; npm install; npm run build; Pop-Location
    Write-Host 'Serving on http://127.0.0.1:8000'
    uv run uvicorn backend.main:app
}
