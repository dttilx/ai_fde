$ErrorActionPreference = 'Stop'
# Non-destructive local drill: restore into a new database, never into apx240.
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$drillId = 'apx_restore_' + [Guid]::NewGuid().ToString('N')
$backupRoot = Join-Path $workspaceRoot '.private/backups'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backupPath = Join-Path $backupRoot ($drillId + '.dump')
$containerDump = '/tmp/' + $drillId + '.dump'
Push-Location $workspaceRoot
try {
    $containerId = (& docker compose ps -q postgres).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $containerId) { throw 'POSTGRES_NOT_RUNNING' }
    & docker exec $containerId pg_dump -U apx_admin -d apx240 -Fc -f $containerDump
    if ($LASTEXITCODE -ne 0) { throw 'DUMP_FAILED' }
    # docker cp preserves binary dumps on Windows; do not redirect binary stdout.
    & docker cp ($containerId + ':' + $containerDump) $backupPath
    if ($LASTEXITCODE -ne 0) { throw 'COPY_FAILED' }
    & docker exec $containerId createdb -U apx_admin $drillId
    if ($LASTEXITCODE -ne 0) { throw 'ISOLATED_DATABASE_CREATE_FAILED' }
    & docker exec $containerId pg_restore -U apx_admin -d $drillId --no-owner --no-acl --exit-on-error $containerDump
    if ($LASTEXITCODE -ne 0) { throw 'RESTORE_FAILED' }
    $checks = [ordered]@{
        migration = "SELECT version_num FROM alembic_version"
        reports = "SELECT count(*) FROM report_versions"
        checkpoints = "SELECT count(*) FROM checkpoints"
        jobs = "SELECT count(*) FROM jobs"
        append_only_triggers = "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE '%append_only%'"
        orphan_reports = "SELECT count(*) FROM report_versions r LEFT JOIN diagnosis_runs d ON r.run_id=d.id WHERE d.id IS NULL"
    }
    $results = [ordered]@{}
    foreach ($key in $checks.Keys) {
        $value = (& docker exec $containerId psql -U apx_admin -d $drillId -At -v ON_ERROR_STOP=1 -c $checks[$key]).Trim()
        if ($LASTEXITCODE -ne 0) { throw ('CHECK_FAILED:' + $key) }
        $results[$key] = $value
    }
    if ($results.migration -ne '0008_feedback_integrity' -or [int]$results.orphan_reports -ne 0 -or [int]$results.append_only_triggers -lt 1) {
        throw 'RESTORED_INTEGRITY_FAILED'
    }
    $record = [ordered]@{
        status = 'DATABASE_RESTORE_PASSED'
        tested_at = [DateTimeOffset]::UtcNow.ToString('o')
        isolated_database = $drillId
        dump_sha256 = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash
        checks = $results
        media_restore = 'NOT_TESTED'
        runtime_recovery = 'NOT_TESTED'
        source_database_modified = $false
    }
    $record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backupRoot ($drillId + '.json')) -Encoding UTF8
    $record | ConvertTo-Json -Depth 4
} finally {
    # Keep the isolated restored DB and private dump for inspection. No destructive cleanup.
    Pop-Location
}
