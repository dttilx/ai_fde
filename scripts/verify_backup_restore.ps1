$ErrorActionPreference = 'Stop'
$backupDir = if ($env:APX_BACKUP_DIR) { $env:APX_BACKUP_DIR } else { '.private/backups' }
if (-not (Test-Path -LiteralPath $backupDir)) {
    Write-Output '{"status":"BLOCKED","reason":"APX_BACKUP_DIR_NOT_PROVIDED"}'
    exit 2
}
$dumps = Get-ChildItem -LiteralPath $backupDir -Filter '*.dump' -File
if ($dumps.Count -eq 0) {
    Write-Output '{"status":"BLOCKED","reason":"NO_DATABASE_DUMP"}'
    exit 2
}
$pgRestore = Get-Command pg_restore -ErrorAction SilentlyContinue
$containerId = $null
if (-not $pgRestore) {
    $containerId = (& docker compose ps -q postgres 2>$null).Trim()
    if (-not $containerId) {
        Write-Output ("{`"status`":`"BLOCKED`",`"reason`":`"PG_RESTORE_NOT_INSTALLED_OR_POSTGRES_UNAVAILABLE`",`"dumps`":{0}}" -f $dumps.Count)
        exit 2
    }
}
foreach ($dump in $dumps) {
    if ($pgRestore) {
        & $pgRestore.Source --list $dump.FullName *> $null
    } else {
        $remote = '/tmp/apx-restore-' + [Guid]::NewGuid().ToString('N') + '.dump'
        & docker cp $dump.FullName ($containerId + ':' + $remote) *> $null
        if ($LASTEXITCODE -ne 0) { Write-Output ("{`"status`":`"FAILED`",`"dump`":`"{0}`",`"reason`":`"COPY_FAILED`"}" -f $dump.Name); exit 1 }
        & docker exec $containerId pg_restore --list $remote *> $null
        $restoreExit = $LASTEXITCODE
        & docker exec $containerId rm -f $remote *> $null
        if ($restoreExit -ne 0) { Write-Output ("{`"status`":`"FAILED`",`"dump`":`"{0}`"}" -f $dump.Name); exit 1 }
    }
    if ($LASTEXITCODE -ne 0) { Write-Output ("{`"status`":`"FAILED`",`"dump`":`"{0}`"}" -f $dump.Name); exit 1 }
}
$result = [ordered]@{
    status = 'READY_FOR_PRIVATE_RESTORE_DRILL'
    dumps = $dumps.Count
    restore = 'list_verified_only'
}
$result | ConvertTo-Json -Compress
