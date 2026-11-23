param(
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '',
    [string]$CatalogPath = '',
    [switch]$Preview
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$source = Join-Path $projectRoot 'nexus_repacks\app.py'
$code = [IO.File]::ReadAllText($source)
$current = [regex]::Match($code, "APP_VERSION = '(\d+\.\d+\.\d+)'").Groups[1].Value
if (-not $current) { throw 'APP_VERSION was not found in app.py.' }
if (-not $Version) {
    $currentVersion = [version]$current
    $Version = '{0}.{1}.{2}' -f $currentVersion.Major, $currentVersion.Minor, ($currentVersion.Build + 1)
}
if ([version]$Version -le [version]$current) { throw "Choose a version newer than $current." }
Write-Host "Preparing Nexus $current -> $Version"
if ($Preview) { Write-Output $Version; return }
& $python scripts/publish_nexus_update.py
if ($LASTEXITCODE -ne 0) { throw 'GitHub access check failed.' }
if ($CatalogPath) {
    & $python scripts/sync_nexus_catalog.py $CatalogPath
    if ($LASTEXITCODE -ne 0) { throw 'Invalid catalog or missing artwork. No release was built.' }
}
$code = $code.Replace("APP_VERSION = '$current'", "APP_VERSION = '$Version'")
[IO.File]::WriteAllText($source, $code, [Text.UTF8Encoding]::new($false))
& $python -m unittest discover -s tests -p 'test_nexus*.py' -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $python -m PyInstaller --noconfirm NexusRepacks.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
& $python scripts/prepare_nexus_update.py
if ($LASTEXITCODE -ne 0) { throw 'Signing failed.' }
& $python scripts/publish_nexus_update.py --publish
if ($LASTEXITCODE -ne 0) { throw 'Publication failed. The prepared files remain in dist/nexus-update-release.' }
Write-Host "Nexus $Version published. Existing compatible copies update automatically."
