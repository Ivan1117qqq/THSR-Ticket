param(
    [string]$Python = '.\.venv\windows\Scripts\python.exe',
    [Parameter(Mandatory=$true)][string]$Compiler,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $workspace
try {
    if (-not $SkipTests) {
        & $Python -m pytest -q -p no:cacheprovider --require-desktop
        if ($LASTEXITCODE -ne 0) { throw 'Release tests failed' }
        & $Python -m flake8 -j1 --config .config/flake thsr_ticket scripts/preview_desktop.py scripts/benchmark_records.py scripts/release_metadata.py scripts/installer_fixture.py
        if ($LASTEXITCODE -ne 0) { throw 'Source checks failed' }
    }
    & $Python -m PyInstaller TravelDesk.spec --noconfirm
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }
    & $Compiler installer/TravelDesk.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    & $Python -m scripts.release_metadata --finalize
    if ($LASTEXITCODE -ne 0) { throw 'Release metadata failed' }
} finally {
    Pop-Location
}
