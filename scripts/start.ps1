param([int]$Port=8080,[switch]$LAN,[switch]$LocalOnly)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$bind=if ($LocalOnly) {'127.0.0.1'} else {'0.0.0.0'}
$nexusArguments=@('--port',$Port,'--bind',$bind)
if ($LocalOnly) {$nexusArguments+='--no-tunnel'}
if (Test-Path dist\NexusView\NexusView.exe) {
    Start-Process -FilePath (Resolve-Path dist\NexusView\NexusView.exe) -ArgumentList $nexusArguments -WindowStyle Hidden
} else {
    & .\.venv\Scripts\python.exe -m host.server @nexusArguments
}
