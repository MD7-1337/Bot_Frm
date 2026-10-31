# Windows 10/11 x64 testing

Source development needs Python 3.12 and the pinned dependencies. Build commands,
portable layout, frozen worker/Monaco smoke and optional installer are documented
in [PACKAGING.md](PACKAGING.md). A source checkout is not a portable release.

For a built portable executable, use
`AndroidAutomationStudio.exe --health-report C:\Users\you\Desktop\studio-health.json`
to save command-line diagnostics. The windowed executable has no console stdout;
the explicit report path makes checks reviewable without launching the workbench.
The GUI Dependency Health command remains available in Settings.

For source use:

```powershell
uv sync --locked --extra test --python 3.12
.venv/Scripts/python.exe tools/fetch_monaco.py
.venv/Scripts/python.exe tools/fetch_adb.py
.venv/Scripts/python.exe tools/fetch_scrcpy.py
.venv/Scripts/python.exe -m app.main --diagnostics
.venv/Scripts/python.exe -m app.main
```

Do not set `QTWEBENGINE_DISABLE_SANDBOX` for normal desktop use. No sudo or
administrator command is required to start the application. OEM USB drivers or
school computer policies may require administrator assistance; application code
cannot grant those permissions. An empty `adb devices -l` output proves no usable
ADB device was discovered at that moment; it does not identify the cause.

Set an explicit executable using `STUDIO_ADB`, or choose it in Settings. Set
`STUDIO_SCRCPY_SERVER` to the exact supported server file when keeping optional
tools outside the application. A Windows path containing spaces is passed as one
subprocess argument; do not add shell quoting characters inside the setting.
Configure an optional local Tesseract installation through Settings; no language
model download is automatic.

Run automated tests with `STUDIO_GUI_TESTS=1` on the Windows desktop. For hosted
CI only, `QT_QPA_PLATFORM=offscreen` and `--disable-gpu` are used. Tests with
simulated devices do not establish USB, Wi-Fi pairing, real scrcpy frames,
rotation, touch, recording or recognition on real Android hardware.

Record Windows build, scaling, GPU/driver, phone model/Android version and exact
tool versions in the acceptance report. Test two independent phones, a disconnect
during automation, emergency stopping, and reopening preserved projects before
promoting this Alpha source increment to Beta.
