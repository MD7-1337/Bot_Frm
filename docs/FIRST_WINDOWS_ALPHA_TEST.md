# First Windows Alpha test

This is a personal test build of Android Automation Studio. Physical Android
behavior is **NOT VERIFIED**. Keep notes about failures so they can be fixed in
later Alpha builds.

## Build the portable app on Windows 10/11 x64

There is currently no approved application binary download. The CI `validation-*`
and `source-tests-*` artifacts contain evidence, not the EXE. Build on your own
Windows PC from the recovery branch:

1. Install [Python 3.12](https://www.python.org/downloads/) with the `py` launcher,
   [Git for Windows](https://git-scm.com/download/win), and `uv==0.12.23`.
   Internet access is needed for the pinned Python packages and Monaco assets.
   Node.js is not needed. In PowerShell:

   ```powershell
   py -3.12 -m pip install --user uv==0.12.23
   uv --version
   git clone https://github.com/MD7-1337/Bot_Frm.git
   cd Bot_Frm
   git switch recovery/continue-alpha-2026-11-01
   .\tools\build-windows-alpha.ps1
   ```

   If `uv` is not found after installation, add Python's user `Scripts` directory
   to your `PATH` and reopen PowerShell. To display it, run
   `py -3.12 -c "import pathlib, site; print(pathlib.Path(site.USER_BASE) / 'Scripts')"`.
   If script execution is restricted, use the same commands in
   [packaging instructions](PACKAGING.md) in the current PowerShell session.

2. The script runs `tools/build_windows.py`, which creates the EXE and ZIP, then
   extracts the ZIP to a temporary location and runs the frozen application smoke
   test. Read `dist\windows-build-manifest.json` and
   `dist\windows-frozen-smoke.json`; both must report `smoke_passed`/`passed` as
   `true`. The smoke covers offline Monaco, Demo Mode, image recognition,
   debugger, recorder, scheduling, project export and restore, and an isolated
   Python worker. The test uses no physical phone.
3. Check the ZIP against `dist\AndroidAutomationStudio-windows-x64-portable.zip.sha256`:

   ```powershell
   Get-FileHash .\dist\AndroidAutomationStudio-windows-x64-portable.zip -Algorithm SHA256
   ```

4. Extract `dist\AndroidAutomationStudio-windows-x64-portable.zip` to a folder
   you own, such as `Documents\Studio Alpha`. Launch
   `AndroidAutomationStudio\AndroidAutomationStudio.exe` inside that folder.
   Keep the `_internal` folder beside the EXE. The extracted app carries Python,
   Qt and Monaco; it starts without Python, Node.js or the repository installed
   on the destination computer. It is unsigned; follow your computer's normal
   execution policy. Save projects outside the extracted application folder.

5. For USB detection, extract Google's official SDK `platform-tools` folder
   beside `AndroidAutomationStudio.exe`, so the path is
   `AndroidAutomationStudio\platform-tools\adb.exe`. Keep the entire folder,
   including its DLLs. Studio detects this path automatically; the build's
   Python virtual environment is not needed on the test computer. If you use
   standalone scrcpy's ADB instead, choose its `adb.exe` in Studio Settings.

On the first normal launch, a dismissible connection wizard explains ADB,
authorization, diagnostics, and preview. It appears once per user settings
profile. Studio still starts in Demo Mode without ADB or a phone.

Optional: install Inno Setup 6 and pass `-Installer` to the build script. The
portable ZIP is enough for the first test. Do not redistribute the personal
build while the third-party review remains open.

## Try the existing features without a phone

1. Open the app and use **Start Demo Session**. The preview is labeled
   **SIMULATED**. No ADB command is sent to a demo identity.
2. Open the Studio workspace. Confirm the Monaco editor loads and syntax colors
   appear. Edit a demo Python script, save it under your project, and run it.
   Approve only code you trust. Watch the preview and execution log.
3. In Visual tools, capture a region from the demo preview, save it under the
   project, insert the image reference in the script and use **Test match on fresh
   frame**. Check the match position and score before running an image click.
4. In Recorder, start recording on the selected demo, use Home/Back or tap the
   preview, stop, inspect the generated Python, save the session, reopen it and
   replay it on the same demo.
5. In Debugger, set a breakpoint in a saved script, start debugging, inspect
   variables and stack, step, continue and stop. Confirm the selected demo is
   idle before starting another run.
6. In Scheduler, create one bounded task for the demo, approve its exact source
   and target, run it once, and inspect history. Avoid a repeating task during
   initial exploration.
7. Save and close the project. Reopen it and confirm scripts, assets, recorder
   sessions and task definitions. Export a project backup and try restoring it
   to another user-owned folder.

## Try a real Android phone when ready — NOT VERIFIED

Install Google's [SDK platform-tools](https://developer.android.com/tools/releases/platform-tools)
and select `adb.exe` in Settings. For video preview, select the pinned scrcpy 3.1
server as described in [Windows installation](INSTALL_WINDOWS.md); Tesseract is
optional for OCR. Enable USB debugging on a phone you may control, connect a data
cable, accept the phone's authorization prompt, then use Device Manager to refresh
and diagnose the exact device. Test a screenshot before live video and touch.
Record all phone results as **NOT VERIFIED** until you actually observe them. The
full one-phone and two-phone checklist is in [hardware acceptance](HARDWARE_ACCEPTANCE.md).

## Report a bug

Use **Device Manager → Diagnostics → Export Bug Report…**. Review the editable,
redacted JSON before saving or sharing. It includes build identity, dependency
health, device states, and recent bounded application events; it does not include
screenshots or script source. The event-log path is shown in Settings → Privacy.
For startup issues, run from PowerShell:

```powershell
.\AndroidAutomationStudio.exe --health-report "$env:TEMP\studio-health.json"
```

Capture a screenshot with Windows Snipping Tool when useful; remove private
screen content, serials and pairing codes. Send the build commit and ZIP SHA-256
from the manifest, Windows version/display scale, exact steps, expected and
actual result, the reviewed bug report, and a screenshot if relevant.

For an empty Device Manager, open Settings and note **Currently selected** ADB.
Use **Device Manager → Diagnose Connection → Export Diagnostics…**. The
**Compare with external adb.exe…** action runs the Studio-selected and
standalone scrcpy ADB executables in the same process environment and shows
their versions and redacted device states side by side. ADB may update its
shared server if the versions differ. Review the comparison before copying it.
You can also run these PowerShell commands with the exact path shown in Studio
Settings (replace the example path):

```powershell
$adbPath = 'C:\path\to\platform-tools\adb.exe'
& $adbPath version
& $adbPath devices -l
Get-ChildItem Env:ADB_SERVER_SOCKET,Env:ANDROID_ADB_SERVER_PORT -ErrorAction SilentlyContinue
```

Compare the output with the ADB executable used by standalone scrcpy, if known.
A custom server environment variable can send either client to a different
server. Do not run `kill-server` during this comparison. Record whether the phone shows as
`device`, `unauthorized`, `offline`, or is absent. Review the diagnostic export
before sharing because paths and serials may identify your computer or phone.
