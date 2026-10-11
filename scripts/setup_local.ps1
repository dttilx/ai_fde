$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path -Parent $PSScriptRoot
$taskEnvPath = Join-Path $taskProjectRoot '.env'
if (-not (Test-Path -LiteralPath $taskEnvPath)) {
    function New-LocalSecret { return [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N') }
    $taskDbAdmin = New-LocalSecret
    $taskDbRuntime = New-LocalSecret
    $taskMediaAdmin = New-LocalSecret
    $taskMediaApp = New-LocalSecret
    @"
POSTGRES_ADMIN_PASSWORD=$taskDbAdmin
POSTGRES_RUNTIME_PASSWORD=$taskDbRuntime
MINIO_ROOT_USER=apx_storage_admin
MINIO_ROOT_PASSWORD=$taskMediaAdmin
MINIO_APP_USER=apx_media_service
MINIO_APP_PASSWORD=$taskMediaApp
DATABASE_URL=postgresql+psycopg://apx_runtime:$taskDbRuntime@127.0.0.1:55432/apx240
MIGRATION_DATABASE_URL=postgresql+psycopg://apx_admin:$taskDbAdmin@127.0.0.1:55432/apx240
STORAGE_PROVIDER=minio
MINIO_ENDPOINT=127.0.0.1:59000
MINIO_BUCKET=apx240-media
PROVIDER_MODE=FIXTURE
COOKIE_SECURE=false
"@ | Set-Content -LiteralPath $taskEnvPath -Encoding UTF8
    Write-Host 'Generated local credentials in ignored .env; values are not printed.'
}
Push-Location $taskProjectRoot
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'Service startup failed; inspect Docker connectivity and image access.' }
} finally { Pop-Location }
