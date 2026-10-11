# Withdraw the project-added enterprise login policy, preserving a backup.
$ErrorActionPreference = 'Stop'
$policy = 'C:\ProgramData\DockerDesktop\admin-settings.json'
if (Test-Path -LiteralPath $policy) {
  $config = Get-Content -LiteralPath $policy -Raw | ConvertFrom-Json
  $expected = @('configurationFileVersion','enableInference','enableInferenceGPUVariant','enableDockerAI')
  if (@($config.PSObject.Properties.Name | Where-Object { $_ -notin $expected }).Count -gt 0) {
    throw 'Additional policy settings found; review required before changing.'
  }
  Move-Item -LiteralPath $policy -Destination ($policy + '.withdrawn-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
Get-Process 'Docker Desktop','com.docker.backend' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe' -WindowStyle Hidden
