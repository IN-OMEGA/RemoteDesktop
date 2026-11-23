# Optional signed virtual controller driver. Never forces a restart.
$ErrorActionPreference='Stop'
$target=Join-Path $env:TEMP 'RemoteCore-ViGEmBus-1.22.0.exe'
Invoke-WebRequest 'https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBus_1.22.0_x64_x86_arm64.exe' -OutFile $target
$sha=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
$signature=Get-AuthenticodeSignature -LiteralPath $target
if ($sha -ne '89220A7865076B342892F98865F3499FB7C4CFD673159E89D352C360FD014C6A' -or $signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Nefarius*') { throw 'Intégrité du pilote refusée' }
$process=Start-Process -FilePath $target -ArgumentList @('/exenoui','/qn','/norestart') -Verb RunAs -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -notin @(0,3010)) { throw "Installation du pilote échouée : $($process.ExitCode)" }
Write-Host 'Pilote installé. Relancez RemoteCore ; un redémarrage Windows peut être requis.'
