# Android Automation Studio

A Windows-targeted desktop IDE for Android visual automation. **The current alpha adds staged connection diagnostics and a workspace redesign to the existing Python/Monaco, ADB/scrcpy and isolated scripting engine. It is not a production release and has not passed real-phone or Windows acceptance.**

Start here: [local testing without sudo, phone diagnostics and first workflows](docs/LOCAL_TESTING.md). The [alpha stabilization report](docs/ALPHA_STABILIZATION.md) separates confirmed code repairs from the user's PC-level USB problem; the [control inventory](docs/CONTROL_INVENTORY.md) records what is verified and what requires hardware.

Start with the [engineering blueprint](docs/BLUEPRINT.md), [technology decisions](docs/DECISIONS.md), [milestones](docs/PHASES.md), and [actual validation results](docs/VALIDATION.md).

For the current implementation and hardware checklist, read [device integration](docs/DEVICE_INTEGRATION.md) and the [pinned scrcpy protocol/lifecycle](docs/STREAMING.md).

The current [scripting API reference](docs/SCRIPTING_API.md) defines every implemented command and error. The [scripting implementation report](docs/SCRIPTING_ENGINE.md) records source changes, actual checks and remaining gates.

The latest [Device Manager and Visual Tools report](docs/DEVICE_MANAGER_VISUAL_TOOLS.md) explains workspace navigation, Wi-Fi connections, the image library, explicit scale matching and the studio-control recorder, including how to test the feature branch before merging.

The original [product specification](docs/PRODUCT_SPECIFICATION.md) is retained for requirement traceability.

## What works in this increment

- PySide6 workspace shell with collapsible navigation, responsive persistent splitters, script tabs/project explorer, atomic save and unsaved-document prompts.
- Consistent light/dark Qt and Monaco appearance, keyboard navigation/command search, settings and an always-present emergency stop.
- Visible Device Manager, Screenshot & Visual Tools and Action Recorder panels, with keyboard navigation, saved names/groups, endpoint-scoped Wi-Fi connect/pair/disconnect, and a browsable project image library.
- Locally bundled Monaco in Qt WebEngine with a restricted QWebChannel bridge, generated API completion/signatures/docs, actual image hover thumbnails, missing-image warnings and execution-line highlighting.
- Serial-specific ADB discovery, connection generations, PNG capture, measured resolution/optional rotation, tap/double-tap/hold/swipe/key controls, and explicit offline/unauthorized/disconnected/unknown states.
- Visible staged connection diagnostics, unreadable permission-denied USB rows, saved ADB path selection, copied redacted reports and actionable school-PC/driver guidance. Diagnostics never bypass OS permissions or kill a shared ADB server.
- Embedded **scrcpy 3.1 H.264 video** transport, actual PyAV decoding, and independent latest-frame Qt previews with adjustable encoder FPS/bitrate/size. Protocol/codec/local-socket fixtures pass; actual Android streaming remains unverified.
- Explicit **ADB screenshot fallback**, polled at a one-second interval when idle. Actual capture latency can be longer. The fallback is labeled separately from video.
- Frozen full-resolution screenshot selection, crop/atomic PNG save, Android coordinates, valid image-based Python command insertion, and asynchronous fresh-frame OpenCV match tests.
- All requested foundational touch, recognition, timing, Android and screen commands, with immutable target objects and project-contained image lookup.
- Independent spawned workers, normal Python/imports/main guards, bounded JSON IPC, per-device leases/generations, trust approval, cancellable waits, pause/resume/stop, tracebacks and an asynchronous Qt service.
- Shared-source and per-phone file assignments with independent contexts, run status and output/error views.
- Tested OpenCV template matching with regions, full-frame coordinates, scores, explicit `Pattern.atScales(...)` and cross-scale overlap suppression.
- A serial-bound recorder of acknowledged studio controls, editable/reorderable Python timeline, JSON session save/open and normal trusted-worker replay. It does not record touches made outside the studio.
- Fresh RGB `getPixel` / `findColor` APIs with regions, explicit tolerance and serial-local contexts.

The workbench always uses the real ADB backend. Mock devices are confined to explicitly identified tests/examples. Missing dependencies/devices produce actionable errors.

**Not implemented yet:** general Python language service, full project backup/import/export management, OCR/UI-element APIs, advanced recorder image conversion/curved multitouch, breakpoint debugger, scheduler, SQLite business persistence, updater, installer or portable Windows build. Task Manager explicitly describes planned scheduling and links to real script assignments.

## Development setup

For **Ubuntu 22.04 x86_64**, follow [README_UBUNTU.md](README_UBUNTU.md) for cloning, system libraries, Python 3.12 setup, desktop startup and the phone-free fixture.

Source development requires Python 3.12 and [uv](https://docs.astral.sh/uv/). The tested environment used uv 0.12.23. The eventual Windows release will bundle Python; that release has not been built. `uv.lock` contains dependency artifact hashes. The installed development environment occupies approximately 1 GB on this Linux machine.

From this repository root, on Windows PowerShell:

```powershell
uv sync --locked --extra test --python 3.12
.venv\Scripts\python.exe tools\fetch_monaco.py
.venv\Scripts\python.exe tools\fetch_adb.py
.venv\Scripts\python.exe tools\fetch_scrcpy.py
.venv\Scripts\python.exe -m app.main
```

These Windows instructions are intended commands, not evidence of a Windows run. On the configured Linux cloud machine:

```bash
cd /workspace/Bot_Frm
bash tools/setup.sh
.venv/bin/python -m app.main --diagnostics
```

On a Linux desktop, launch with `.venv/bin/python -m app.main`. A headless cloud machine has no interactive Windows desktop. Use the tests below for integration verification; do not expect a browser preview of this native application.

Monaco 0.52.2 is downloaded from npm and checked against its pinned SHA-512 integrity digest. No Node runtime is needed. The ADB helper installs platform-tools 37.0.1 under `.tools/`, checking Google's SDK metadata checksum. The scrcpy helper verifies the official 3.1 server SHA-256. Both default and custom server paths are checked at session start. Downloads retain TLS verification. Third-party redistribution, including PyAV's linked FFmpeg build, still requires the audit in [DECISIONS.md](docs/DECISIONS.md). Generated dependencies are ignored by Git and reproduced by these setup commands.

Core editing and worker execution do not require internet after setup. Physical devices require local USB/ADB or configured Wi-Fi communication. No account or telemetry is required.

## Connect and use a device

1. Enable Developer Options and USB debugging on a phone you are authorized to control.
2. Connect USB; accept the phone's debugging authorization prompt. Windows may require the manufacturer's USB driver.
3. Select **Refresh devices**. Unauthorized/offline entries are shown and cannot be controlled.
   Open **Workspaces → Device Manager** (`Ctrl+2`) for connection guidance, saved names/groups and Wi-Fi controls. For Android 11+ Wireless debugging, pair using its pairing port/code, then connect using its separate connection port. USB disconnection is physical; Wi-Fi Disconnect targets only the selected host:port.
4. Select an authorized device, choose encoder settings and **Start live**. **Start all connected** requests independent streams (default cap: four). Stop a stream before changing its settings. Use **Screenshot fallback** explicitly if streaming is unavailable; failed video is never presented as a live connection.
5. Tap, double tap, hold or drag inside a preview; letterboxes do not send input. Background tiles target their own serial. Home and Back target the selected row. A short single tap waits through Qt's double-click interval to distinguish it from a double tap. Drag is a supported ADB press/move/release swipe, not a continuous raw-touch path.
6. Choose **File → Choose project image library…** and select the project root. **Capture image region…** (`Ctrl+Shift+C`) freezes an original-resolution PNG while video continues. Save defaults to `project/images`; insertion generates a plain Python path assignment followed by `click(image_path)`. Test Match shows scores and tap positions without sending input.
   **Screenshot & Visual Tools** (`Ctrl+3`) also browses existing targets, inserts configured Pattern commands and tests them on a new phone capture. **Capture PNG…** always saves a new original-resolution screenshot, including when video is scaled.
7. Edit a script using the API below, then F5/**Run trusted script…** on the current phone. Ctrl+F5 runs the same source independently on selected device rows. **Execution → Assign Python file… / Run assigned files…** supports different source files per phone. Approve the exact source snapshots and serials; manual controls for those phones are blocked while workers own them.
8. Use **Emergency stop** or `Ctrl+Shift+F12` to latch stopping; reset explicitly before allowing new input/runs. Disconnect/unknown states invalidate only that phone's queued work and workers. Reconnect and start again explicitly; old work is not replayed. An already-sent Android command cannot be undone.

Set `STUDIO_ADB` to an explicit executable path when needed. Otherwise the application tries PATH, then its verified local tools. `STUDIO_SCRCPY_SERVER` may select a local server file but must match the exact pinned artifact. The native scrcpy desktop executable is optional. Wi-Fi connect/pair UI remains later-phase work; an already connected Wi-Fi ADB serial can be discovered. Do not expose an unauthenticated ADB port to untrusted networks.

Select a row under **Script runs** and use F6 to pause, Shift+F6 to resume, or Shift+F5 to stop it. Pause is acknowledged only at a safe point; native calls can delay acknowledgment. Editing source clears its stale execution-line decoration. Project choice and file assignments are session context, not a persistent task scheduler.

## Foundational script API

The following functions are bound to each run's assigned device:

```python
target = Pattern("start.png").similar(0.9).targetOffset(2, -1)
if exists(target):
    click(target)
wait(2)                       # cancellable numeric delay
reward = device.waitImage("reward.png", timeout=10)
device.click(reward)           # same implementation, assigned phone
print(getDevice(), getResolution())
```

Scripts are ordinary trusted Python with host-user permissions. Process isolation is **not a security sandbox** and cannot stop arbitrary imports, external ADB clients, or script-created descendants. GUI approval is never exposed through the web bridge. Leases coordinate this app's built-in operations, not other programs.

The implemented API includes `click`, `doubleClick`, `longPress`, `tap`, `swipe`, `drag`, `scroll`, `find`, `findAll`, `exists`, `waitImage`, `waitVanish`, `sleep`, overloaded `wait`, `back`, `home`, `launchApp`, `stopApp`, supported `typeText`, `capture`, `getResolution` and compatible serial-returning `getDevice`. All are also methods on `device`. See [SCRIPTING_API.md](docs/SCRIPTING_API.md) for signatures, return values, image paths, ambiguity and timeout rules. OCR and other broader blueprint APIs remain future work.

To run the two-worker proof without phones:

```bash
.venv/bin/python -m examples.two_devices
.venv/bin/python -m examples.run_visual_fixture
```

These examples explicitly use fixture serials and mock backends. The visual example generates known PNGs and executes both scripting styles in separate actual worker processes. They do not establish physical phone control.

## Tests

```bash
.venv/bin/python -m pytest -q
```

The real GUI tests are opt-in. On Linux headless infrastructure:

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu' \
XDG_CONFIG_HOME=/tmp/aas-qt-tests .venv/bin/python -m pytest -q
```

The browser sandbox override is limited to this isolated headless test environment. **Do not set it for normal desktop use.** This cloud command also needs execution outside its command sandbox because Chromium and multiprocessing require local IPC. Graphics-context warnings occur without a GPU; the tests verify actual editor behavior and exit status. On a normal Windows desktop, set only `STUDIO_GUI_TESTS=1` before running pytest.

See [SCRIPTING_ENGINE.md](docs/SCRIPTING_ENGINE.md) for current measured outcomes, [VALIDATION.md](docs/VALIDATION.md) for the historical baseline, and [DEVELOPMENT.md](docs/DEVELOPMENT.md) for developer guidance.
