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
$startMenu = [Environment]::GetFolderPath('StartMenu')
$shortcut = Join-Path $startMenu "Programs/Android Automation Studio/Android Automation Studio.lnk"
if (-not (Test-Path $shortcut)) { throw "Per-user Start menu shortcut missing" }
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcut)
if ([IO.Path]::GetFullPath($link.TargetPath) -ne [IO.Path]::GetFullPath($exe)) { throw "Shortcut targets incorrect executable" }
# Exercise the existing-install upgrade path with the same Alpha version. A
# different-version upgrade still needs a previous distributable baseline.
$upgrade = Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$installDir`"") -Wait -PassThru
if ($upgrade.ExitCode -ne 0) { throw "Existing-install upgrade failed: $($upgrade.ExitCode)" }
if (-not (Test-Path $marker)) { throw "Upgrade removed external user project" }
$report = (Join-Path (Get-Location) "dist/windows-installed-smoke.json")
$smoke = Start-Process -FilePath $exe -ArgumentList @('--release-smoke-report', "`"$report`"") -Wait -PassThru
if ($smoke.ExitCode -ne 0) { throw "Installed application smoke failed: $($smoke.ExitCode)" }
$result = Get-Content -Raw $report | ConvertFrom-Json
if (-not $result.passed -or -not $result.frozen) { throw "Installed application report did not confirm frozen success" }
$uninstaller = Join-Path $installDir "unins000.exe"
$removed = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
if ($removed.ExitCode -ne 0) { throw "Uninstaller failed: $($removed.ExitCode)" }
if (-not (Test-Path $marker)) { throw "Uninstaller removed external user project" }
if (Test-Path $exe) { throw "Uninstaller left application executable" }
if (Test-Path $shortcut) { throw "Uninstaller left Start menu shortcut" }
@{ passed = $true; per_user = $true; elevated_install_required = $false; project_preserved = $true; start_menu_shortcut = $true; same_version_upgrade = $true; different_version_upgrade = "NOT VERIFIED"; signed = $false } |
    ConvertTo-Json | Set-Content -Encoding utf8 "dist/windows-installer-validation.json"
