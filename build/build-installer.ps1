# Genera el instalador de GuiaClick con Inno Setup. Reconstruye el dist por
# defecto; -SkipBuild lo reutiliza. Version = APP_VERSION (fuente unica).
param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$distExe = Join-Path $root "dist\GuiaClick\GuiaClick.exe"

if ($SkipBuild -and (Test-Path $distExe)) {
    Write-Host "Reutilizando dist (-SkipBuild)." -ForegroundColor DarkGray
} else {
    & (Join-Path $PSScriptRoot "build.ps1")
    if ($LASTEXITCODE -ne 0) { Write-Host "Fallo el build." -ForegroundColor Red; exit 1 }
}
if (-not (Test-Path $distExe)) { Write-Host "No existe el dist; abortando." -ForegroundColor Red; exit 1 }

$initPy = Join-Path $root "guiaclick\__init__.py"
$m = Select-String -Path $initPy -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $m) { Write-Host "ERROR: no se encontro APP_VERSION." -ForegroundColor Red; exit 1 }
$ver = $m.Matches[0].Groups[1].Value
Write-Host "Version: $ver" -ForegroundColor Green

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                     "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                     "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if (-not $iscc) {
    Write-Host "No se encontro Inno Setup (ISCC.exe). winget install JRSoftware.InnoSetup" -ForegroundColor Red
    exit 1
}
& $iscc "/DMyAppVersion=$ver" (Join-Path $PSScriptRoot "GuiaClick.iss")
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nInstalador: $(Join-Path $root ("installer\GuiaClick-Setup-$ver.exe"))" -ForegroundColor Green
} else {
    Write-Host "Fallo el instalador (codigo $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
