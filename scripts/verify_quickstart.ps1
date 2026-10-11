$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    Write-Host 'Checking PostgreSQL/pgvector and MinIO health...'
    docker compose ps
    if ($LASTEXITCODE -ne 0) { Write-Output '{"status":"BLOCKED","reason":"DOCKER_UNAVAILABLE"}'; exit 2 }
    Push-Location backend
    try {
        uv run alembic current
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        uv run pytest -q tests/acceptance/test_a203.py tests/acceptance/test_safety.py tests/acceptance/test_a310.py tests/acceptance/test_media_candidates.py tests/acceptance/test_expert_feedback.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Pop-Location }
    Write-Host 'Fixture quickstart checks passed. Real providers remain a separate, permission-gated run.'
} finally { Pop-Location }
