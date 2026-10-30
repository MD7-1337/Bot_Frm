# feat: add Device Manager, visual library and control recorder

The GUI exposed devices as a basic list and capture tools mainly through a
crowded toolbar. This change adds visible workspace navigation and dedicated
Device Manager, Screenshot & Visual Tools and Action Recorder docks, while
preserving Python/PySide6, Monaco/QWebChannel, ADB, scrcpy/PyAV and worker isolation.

## Features and fixes

- Endpoint-scoped Wi-Fi connect/pair/disconnect, USB guidance, exact serial/state
  details, saved device names/groups, group selection and existing multi-phone Run.
- Preserve multiple selections and user selection changes during ADB discovery;
  retain disconnected identities and recover safely after failed disconnects.
- Browse contained project image assets, preview thumbnails, insert configured
  Pattern calls into Monaco and test existing targets on fresh phone captures.
- Save fresh full-resolution PNGs even when the video preview is scaled; cancel
  queued region captures when their project/script context changes.
- Explicit `Pattern.atScales(...)`, actual multi-scale OpenCV recognition and
  cross-scale overlap suppression with unchanged default single-scale behavior.
- Record acknowledged studio controls for one serial/generation; pause/stop,
  edit/reorder/delete Python steps and insert into Monaco for normal trusted replay.
  Failed/obsolete completions are excluded; disconnect/emergency stop ends recording.
- Separate emergency toolbar and improved editor/dock sizing. Existing trust
  approval, global stop, connection generations and independent workers remain.

## Files

New application modules: `app/ui/device_manager.py`, `visual_tools.py`,
`recorder_panel.py`, `app/automation/recording.py`.

Updated application files: `app/ui/window.py`, `capture_dialog.py`,
`app/devices/adb.py`, `app/vision/matching.py`, `app/automation/api/device.py`,
`models.py`, `app/editor/catalog.py`, `widget.py`, `app/main.py`.

Six new test/probe files and two extended existing tests accompany the changes.
README, Ubuntu instructions, API, architecture/status documentation and fixture
screenshots are updated. No dependency pins or installer changes.
The [full report and inventory](https://github.com/MD7-1337/Bot_Frm/blob/feat/device-manager-visual-tools/docs/DEVICE_MANAGER_VISUAL_TOOLS.md)
contains contracts and real-device acceptance steps.

## Validation

**569 passed, 0 failed, 0 skipped** on Linux x86-64, Python 3.12.14 / PySide6 6.8.3.
The full suite enables real Qt/Monaco tests, OpenCV/H.264/socket tests and spawned
workers. The previous 496 tests remain, with extended dock/catalog expectations;
73 new tests include the integrated GUI workflow and independent recording replay.
Compileall and diff whitespace checks pass. ADB discovery returned `[]`.

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu \
XDG_CONFIG_HOME=/tmp/aas-device-tools-acceptance .venv/bin/python -m pytest -q
```

The browser flags above are only for isolated headless cloud tests, never normal
desktop startup. There is no physical Android or Windows validation claim.

## GUI screenshots

Actual Qt widgets with explicitly labeled fixture phones and synthetic pixels:

![Device Manager fixture](https://raw.githubusercontent.com/MD7-1337/Bot_Frm/feat/device-manager-visual-tools/docs/screenshots/devices-fixture.png)
![Visual Tools fixture](https://raw.githubusercontent.com/MD7-1337/Bot_Frm/feat/device-manager-visual-tools/docs/screenshots/visual-fixture.png)
![Recorder fixture](https://raw.githubusercontent.com/MD7-1337/Bot_Frm/feat/device-manager-visual-tools/docs/screenshots/recorder-fixture.png)

## Windows compatibility and limits

Windows 10/11 x64 remains the target; only Linux was tested. Windows drivers,
clean deployment, native spawn, DPI/monitor transitions and hardware behavior
remain acceptance gates. No Windows installer is included.

No real phones were available. Actual Wi-Fi pairing, Android video/input,
rotation, two-phone behavior and failure timing need hardware validation.
Recorder timelines are session-only until inserted/saved, cover studio controls
only and use approximate dispatch timing. Gesture replay uses supported endpoint
ADB swipes, not raw multitouch. Explicit scales add native matching cost; they do
not implement OCR or general scale/lighting independence. Library scans are
bounded and refresh explicitly after external changes. See the report for limits.

## Remaining work and review

Test on two real phones over USB/Wi-Fi on Ubuntu 22.04 and Windows 10/11, including
rotation, reduced video size versus original PNG, match settings, recorder replay,
disconnect/pair failures and emergency stop. OCR/UI hierarchy, richer telemetry,
advanced recorder persistence/image conversion, debugger and scheduling remain.

**User review is required before merging. Leave this feature branch and PR
unmerged; do not delete the branch or change main/branch protection settings.**
