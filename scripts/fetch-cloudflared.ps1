param()
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$directory=Join-Path $root 'third_party\cloudflared'
$target=Join-Path $directory 'cloudflared.exe'
$expected='341deda3db5ec498a0482254d6c38c0b7cf01a30c37bb5dd95d2216d08955e35'
$url='https://github.com/cloudflare/cloudflared/releases/download/2026.11.1/cloudflared-windows-amd64.exe'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
if (!(Test-Path -LiteralPath $target)) {
    Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower() -ne $expected) {
    throw 'Le SHA-256 de cloudflared ne correspond pas à la version officielle attendue.'
}
Write-Output 'cloudflared 2026.11.1 vérifié.'
