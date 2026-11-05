# Windows 10/11 x64 independent testing

The developer packages target Windows 10/11 x64 and bundle Python, Qt/WebEngine,
Monaco, recognition, video decoding and the worker runtime. The recipient does
not need Python, Node.js or a source checkout. Source version is 0.2.0 Alpha;
inspect [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md) for the actual artifacts
and platform results. A build recipe is not evidence that a Windows binary exists.

## Current download status

**Application downloads are blocked pending licensing clearance.** Native CI has
built and smoke-tested a real unsigned Windows EXE, ZIP and installer. Artifacts
named `validation-*` or `source-tests-*` contain evidence, not the application.
See [current validation](RELEASE_VALIDATION.md) for the exact source acceptance
status and remaining license obligations. No approved Windows binary download is
currently offered.

For a personal Windows-native build and first hands-on test, follow
[FIRST_WINDOWS_ALPHA_TEST.md](FIRST_WINDOWS_ALPHA_TEST.md).

## Download and launch after clearance

1. Open [the cross-platform workflow](https://github.com/MD7-1337/Bot_Frm/actions/workflows/cross-platform-alpha.yml)
   and choose the run for `recovery/continue-alpha-2026-11-01` and the desired
   commit. Read its Windows job and source/packaged validation evidence.
2. Download `AndroidAutomationStudio-windows-x64-<commit>` from that run.
   GitHub normally requires signing in for Actions artifact downloads. These are
   expiring developer-review artifacts, not an automatically published stable
   release. Publication requires passing source and redistribution gates. Do not treat
   validation-only artifacts as an application download.
3. Extract the outer Actions artifact. Check the inner
   `AndroidAutomationStudio-windows-x64-portable.zip` against its `.zip.sha256`
   sidecar:

   ```powershell
   Get-FileHash .\AndroidAutomationStudio-windows-x64-portable.zip -Algorithm SHA256
   ```

4. Extract that ZIP into a user-owned directory. Run
   `AndroidAutomationStudio\AndroidAutomationStudio.exe`. Keep `_internal`
   alongside the executable. Move the entire folder when relocating it.
5. Open Monaco and **Start Demo Session**. Demo Mode is explicitly simulated and
   needs no ADB or phone. Create projects outside the installation directory.

Artifacts are unsigned unless their validation report explicitly says otherwise.
Windows may display a reputation warning. Verify the source/checksum and follow
your organization's execution policy; do not bypass administrator restrictions.
Do not add Chromium sandbox-disable environment variables to desktop launchers.
Headless CI overrides are not application defaults.

## Optional per-user installer

If present, verify `AndroidAutomationStudio-windows-x64-setup.exe` against its
`.exe.sha256` sidecar. It installs for the current user under
`%LOCALAPPDATA%\Programs\AndroidAutomationStudio`, creates a Start Menu shortcut
and offers a desktop shortcut. Normal per-user installation does not require
administrator privileges. The recipe does not delete user settings or external
projects during upgrade/uninstall; keep projects outside the payload directory.

An installer exists only after a real compiler run. CI additionally installs it
into an isolated directory, tests the installed frozen application, then
uninstalls while checking that an external project marker survives. Hosted-runner
testing does not replace clean Windows 10/11 desktop acceptance.

## Android and optional OCR

ADB/platform-tools, scrcpy server and Tesseract are external by default; Android
SDK bundling requires artifact-specific terms/notices review. No binary or OCR
model is silently downloaded.

- Obtain Google's official [SDK platform-tools](https://developer.android.com/tools/releases/platform-tools)
  and choose `platform-tools\adb.exe` in Settings if automatic selection fails.
- Select the official scrcpy **3.1 server** in Settings. Its exact pinned checksum
  must match; incompatible versions are not silently substituted.
- Optional OCR needs a trusted local Tesseract engine/languages selected in Settings.
  Image/color recognition and Demo Mode work without it.
- USB needs a data cable, USB debugging and phone authorization. Some phones need
  an OEM USB driver. Empty discovery can be a host/cable/driver/policy problem.

Use the Connection Wizard and **Diagnose Connection** first. Follow
[REAL_ANDROID_TESTING.md](REAL_ANDROID_TESTING.md) on an authorized computer;
the restricted school PC is not an acceptance prerequisite.

## Diagnostics

Use Settings/Help dependency health and Device Manager's redacted diagnostic
export. The windowed executable can save a report without a console:

```powershell
.\AndroidAutomationStudio.exe --health-report "$env:TEMP\studio-health.json"
```

Review reports before sharing. Include Windows build, package commit/checksum,
scaling and the failed step. Screenshots can contain private content; pairing
codes must not appear in reports. Trusted Python retains your OS permissions.
