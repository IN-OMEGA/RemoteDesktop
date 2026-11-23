param([switch]$Package)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$vc='D:\visualCode\Product\VC\Auxiliary\Build\vcvars64.bat'
$cmake='D:\visualCode\Product\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
if (!(Test-Path -LiteralPath $vc)) {
    $vswhere="${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $nexusVsInstall=$null
    if (Test-Path -LiteralPath $vswhere) {
        $nexusVsInstall=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    }
    if ($nexusVsInstall) {
        $vc=Join-Path $nexusVsInstall 'VC\Auxiliary\Build\vcvars64.bat'
        $cmake=Join-Path $nexusVsInstall 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
    }
}
if ((Test-Path -LiteralPath $vc) -and (Test-Path -LiteralPath $cmake)) {
    & cmd /c "`"$vc`" >nul && `"$cmake`" -S . -B build -G `"NMake Makefiles`" -DCMAKE_BUILD_TYPE=Release && `"$cmake`" --build build"
    if ($LASTEXITCODE -ne 0) { throw 'Compilation C++ échouée' }
} else {
    $nexusNativeDll=Get-Item -LiteralPath build\RemoteCoreCapture.dll -ErrorAction SilentlyContinue
    $nexusNativeSources=@(Get-ChildItem src -Recurse -File)+@(Get-Item CMakeLists.txt)
    if (!$nexusNativeDll -or ($nexusNativeSources | Where-Object LastWriteTimeUtc -GT $nexusNativeDll.LastWriteTimeUtc)) {
        throw 'MSVC est introuvable et la DLL native doit être reconstruite. Installez les outils C++ Visual Studio.'
    }
    Write-Output 'MSVC indisponible : réutilisation de la DLL native existante, plus récente que les sources C++.'
}
if (!(Test-Path .venv\Scripts\python.exe)) { & py -3.12 -m venv .venv }
$env:VGAMEPAD_SKIP_VIGEMBUS_INSTALL='true'
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances échouée' }
if ($Package) {
    & powershell -ExecutionPolicy Bypass -File scripts/fetch-cloudflared.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Vérification de cloudflared échouée' }
    & .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name NexusView --icon assets/nexus.ico --version-file assets/version_info.txt --add-data 'web;web' --add-data 'assets;assets' --add-data 'third_party/cloudflared/LICENSE;licenses/cloudflared' --add-binary 'third_party/cloudflared/cloudflared.exe;tools' --add-binary 'build/RemoteCoreCapture.dll;native' --collect-all soundcard --collect-all vgamepad --collect-all customtkinter --hidden-import PIL._tkinter_finder --hidden-import pystray._win32 --hidden-import host.server --hidden-import host.capture --hidden-import host.audio --hidden-import host.encoder --hidden-import host.remote_input --hidden-import host.host_ui host/server.py
    if ($LASTEXITCODE -ne 0) { throw 'Création de l’exécutable échouée' }
    Copy-Item -LiteralPath README.md -Destination dist\NexusView\README.md
    Copy-Item -LiteralPath docs -Destination dist\NexusView\docs -Recurse -Force
}
