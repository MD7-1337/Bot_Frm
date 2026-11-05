param(
    [switch]$Prepared,
    [switch]$Installer
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'This build requires Windows x64.'
}
if (-not $Prepared) {
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne 'recovery/continue-alpha-2026-11-01') {
        throw "Check out recovery/continue-alpha-2026-11-01 before building (current: $branch)."
    }
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        throw 'Install uv 0.12.23 first: py -3.12 -m pip install --user uv==0.12.23, then add the Python user Scripts directory to PATH.'
    }
    & uv --version
    if ($LASTEXITCODE -ne 0) { throw 'uv did not start.' }
    & uv sync --locked --extra test --python 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Pinned environment installation failed.' }
    & uv pip install --python .venv/Scripts/python.exe PyInstaller==6.12.0
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
    & .\.venv\Scripts\python.exe tools/fetch_monaco.py
    if ($LASTEXITCODE -ne 0) { throw 'Verified Monaco download failed.' }
}

$arguments = @('tools/build_windows.py')
if ($Installer) { $arguments += '--installer' }
& .\.venv\Scripts\python.exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'Windows build or extracted EXE smoke test failed.' }
Write-Host 'Built and smoke-tested dist/AndroidAutomationStudio-windows-x64-portable.zip'
Write-Host 'Run dist/AndroidAutomationStudio/AndroidAutomationStudio.exe after extracting the ZIP.'
