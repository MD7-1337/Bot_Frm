$studioRoot = Split-Path -Parent $PSScriptRoot
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $studioPython)) {
    Write-Error 'Python environment missing. Follow docs/LOCAL_TESTING.md to run uv sync --locked --extra test --python 3.12.'
    exit 1
}
Push-Location $studioRoot
try {
    & $studioPython -m app.main @args
    $studioExit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $studioExit
