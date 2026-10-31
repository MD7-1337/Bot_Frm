# Actual per-user install / frozen smoke / uninstall on a Windows CI runner.
$ErrorActionPreference = "Stop"
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("studio-install-test-" + [guid]::NewGuid())
$installDir = Join-Path $testRoot "installed app with spaces"
$projectDir = Join-Path $testRoot "preserved projects"
New-Item -ItemType Directory -Path $projectDir -Force | Out-Null
$marker = Join-Path $projectDir "preserve.txt"
Set-Content -Path $marker -Value "user project survives uninstall"
$setup = (Resolve-Path "dist/AndroidAutomationStudio-windows-x64-setup.exe").Path
$installed = Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$installDir`"") -Wait -PassThru
if ($installed.ExitCode -ne 0) { throw "Installer failed: $($installed.ExitCode)" }
$exe = Join-Path $installDir "AndroidAutomationStudio.exe"
$report = (Join-Path (Get-Location) "dist/windows-installed-smoke.json")
$smoke = Start-Process -FilePath $exe -ArgumentList @('--release-smoke-report', "`"$report`"") -Wait -PassThru
if ($smoke.ExitCode -ne 0) { throw "Installed application smoke failed: $($smoke.ExitCode)" }
$result = Get-Content -Raw $report | ConvertFrom-Json
if (-not $result.passed -or -not $result.frozen) { throw "Installed application report did not confirm frozen success" }
$uninstaller = Join-Path $installDir "unins000.exe"
$removed = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
if ($removed.ExitCode -ne 0) { throw "Uninstaller failed: $($removed.ExitCode)" }
if (-not (Test-Path $marker)) { throw "Uninstaller removed external user project" }
@{ passed = $true; per_user = $true; elevated_install_required = $false; project_preserved = $true; signed = $false } |
    ConvertTo-Json | Set-Content -Encoding utf8 "dist/windows-installer-validation.json"
