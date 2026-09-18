# Run from the repo root:
#   powershell -File .\scripts\start-operator.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Starting database and Redis..."
# Only db + redis here. Worker/Beat run in this script with --pool=solo for Windows.
# (Full `docker compose up -d` also starts Linux container workers — use that on a VPS.)
docker compose up -d db redis

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Create a virtualenv first: python -m venv .venv"
    exit 1
}

Write-Host "Applying database updates..."
& $venvPython manage.py migrate

$frontend = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing operator UI..."
    Push-Location $frontend
    npm install
    Pop-Location
}

function Start-OperatorWindow([string]$Title, [string]$Command) {
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$Root'; Write-Host '$Title'; $Command"
    )
}

Start-OperatorWindow "Django API" ".\.venv\Scripts\Activate.ps1; python manage.py runserver 127.0.0.1:8000"
Start-OperatorWindow "Celery worker" ".\.venv\Scripts\Activate.ps1; celery -A config worker -l info --pool=solo"
Start-OperatorWindow "Celery beat" ".\.venv\Scripts\Activate.ps1; celery -A config beat -l info"
Start-OperatorWindow "Phone Desk UI" "Set-Location '$frontend'; npm run dev"

Write-Host ""
Write-Host "Phone Desk: http://127.0.0.1:3000"
Write-Host "API / admin: http://127.0.0.1:8000/admin/"
Write-Host "Sign in with the same username you created via createsuperuser."
