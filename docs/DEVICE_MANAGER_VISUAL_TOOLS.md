# Device Manager, visual tools and recorder increment

Historical stage: the subsequent [alpha stabilization](ALPHA_STABILIZATION.md)
supersedes the layout, adds diagnostics and recorder sessions, and records the
latest test evidence. The report below describes its original feature commit.

Date: 2026-10-30. Development version remains 0.2.0. Windows 10/11 x64 is the
final target. This increment was exercised on Linux; it is not Windows or
physical Android acceptance.

## Audit and delivered behavior

The existing application had a dock named Devices containing only a list.
Capture actions lived in an overflowing device/execution toolbar, and a saved
layout could hide their related docks. There was no browsable image library or
recorder interface. Monaco, serial-bound ADB, scrcpy/PyAV, capture/crop matching
and isolated scripting workers already worked and remain in use.

- A visible **Workspaces** menu and navigation toolbar focus **Script Studio**
  (`Ctrl+1`), **Device Manager** (`Ctrl+2`), **Screenshot & Visual Tools**
  (`Ctrl+3`) and **Action Recorder** (`Ctrl+4`). These commands reopen hidden
  docks; View retains individual dock toggles and Reset layout. The editor stays
  central. Panels are dockable and side controls scroll on smaller displays.
- Device Manager shows serial, model, actual connection state, available screen
  dimensions/orientation, assigned script, state-specific troubleshooting,
  saved display names/groups and group selection. Names are presentation labels;
  routing always uses ADB serials. Periodic discovery preserves multiple selected
  phones and selection changes made while discovery was in flight. In-progress
  name edits are preserved. Unavailable selections never jump to another phone.
- USB authorization guidance and explicit **host:port** Wi-Fi Connect, Pair and
  Disconnect controls are available. Android 11+ pairing requires a separate
  pairing port/code; after pairing use the connection port. Operations run in
  the thread pool with finite ADB deadlines and acknowledgment checks, then
  refresh device discovery. A connected transport is not assumed authorized.
  USB drivers/udev access are still supplied by the host. Pairing codes are not
  logged or saved; the six-digit code necessarily exists briefly in ADB's local
  process arguments. Network disconnect never uses ADB's disconnect-all command.
- Screenshot & Visual Tools browses the selected project's `images/` directory,
  including nested names. Thumbnails decode off the GUI thread using the same
  canonical containment boundary as scripting. Unsupported/missing assets fail
  explicitly. Scans stop at 500 images, 5,000 files or 2,000 visited directories;
  symlink directories are not traversed. There is no automatic filesystem watcher:
  use Refresh after external changes; capture saves refresh automatically.
- Buttons capture regions, save a full screenshot, select a project, insert
  image paths or `click`/`find`/`waitImage` commands into Monaco, and test saved
  targets on a new full-resolution device capture. Generated Pattern code
  preserves thresholds, signed offsets, explicit scales and optional original
  screen search bounds. Existing editor assistance and image hovers remain.
- The capture dialog tests either a newly selected crop or a saved library image.
  Its tester supports explicit scales and an optional drawn search rectangle,
  separate frozen-source/fresh-result views, scores, coordinates, ambiguity and
  no-match reporting. It never taps a result. Target offsets affect inserted
  script actions; tester overlays describe match centers and bounds.
- `Pattern(...).atScales(0.75, 1, 1.25)` adds explicit multi-scale OpenCV matching
  to the real scripting API and Monaco catalog. Default `(1.0,)` preserves the
  existing path. Bounds are original screenshot pixels; target offsets remain
  original pixels, not scaled offsets. Cross-scale overlap suppression removes
  duplicate detections. Similarity is correlation, not a correctness probability.
- The recorder binds to one serial and connection generation. It records only
  successfully acknowledged preview taps, double taps, stationary long presses,
  endpoint swipes/drags, Home and Back, plus approximate gaps between commands.
  Actions from other phones, paused capture, failed commands and obsolete
  completion tickets do not enter its timeline. Disconnect, emergency stop,
  script execution on the recorded phone and window closing stop capture.
- Stop recording to edit Python calls, delete/reorder rows and insert into Monaco.
  Generate/save/run through the existing editor and trusted worker workflow.
  No execution occurs during timeline editing or insertion. Captured image
  references can replace coordinate actions in Monaco. The recorder does not
  observe physical touches outside the studio, capture curved paths/multitouch,
  record automatic script actions, or convert coordinates into images by itself.
- Emergency controls have their own toolbar. Monaco's view receives layout
  stretch instead of giving unused space to its execution-status label. The
  recorded timeline does not force a large minimum-height bottom panel.

## Correctness fixes

1. Discovery no longer collapses multi-selection or restores stale selection.
2. Full screenshot saving captures a new original-resolution PNG instead of
   exporting a scaled video preview. Capture/write run off the GUI thread and
   reject a changed connection; an already saved PNG remains a historical image.
3. Queued region captures bind the project/script at request time and cancel if
   context changes. An `images` symlink escaping the project is rejected before
   creating the capture directory. Canonical containment is not an OS sandbox
   against concurrent hostile filesystem changes.
4. A requested Wi-Fi disconnect invalidates queued input, workers and preview
   state before removing that one endpoint. A subsequent successful discovery
   can establish a fresh control token even if disconnect failed; previews and
   recordings still require an explicit restart.
5. Recorder pause/stop/session tickets invalidate late completions, and failure
   stops recording rather than emitting a successful generated step.

## Validation

Final command from the repository root:

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu \
XDG_CONFIG_HOME=/tmp/aas-device-tools-acceptance .venv/bin/python -m pytest -q
```

**569 passed, 0 failed, 0 skipped; exit 0; 23.98 seconds.** The original 496 tests
remain, with the expected dock count extended from 3 to 5 and Pattern catalog
assertions extended to include `atScales`. The 73 added tests exercise the new
work, including the integrated workflow probe. An initial run found those two
obsolete expectations; both were updated, and the final full run has no failures.

`python -m compileall -q app examples tools tests` and `git diff --check` pass.
`python -m app.main --diagnostics` reports all four workspaces, recorder/scales
capabilities, local Monaco and a verified scrcpy 3.1 server. Actual
`AdbClient.devices()` returned **[]**. No physical Android device was tested.

Platform exercised: Linux x86-64, kernel 6.18.55, glibc 2.41; Python 3.12.14,
PySide6 6.8.3, Monaco 0.52.2, NumPy 2.2.4, OpenCV-headless 4.11.0.86,
PyAV 14.2.0 and pytest 8.3.5. Ubuntu 22.04 setup instructions are provided;
this cloud run is not an Ubuntu 22.04 or Windows acceptance result. Headless
Qt/WebEngine and IPC tests used the platform's supported escalated execution.
Browser sandbox disabling is only for this isolated headless test environment,
never normal desktop startup. Headless GPU warnings did not prevent assertions.

The new real Qt/Monaco probe uses explicitly injected fixture devices, images
and stream objects. It checks visible navigation/buttons, group persistence,
selection during delayed discovery, unavailable states, endpoint-scoped network
calls off the GUI thread, template thumbnails/insertion, fresh match testing,
full-resolution saving and recorder editing/insertion/disconnect/emergency paths.
Separate tests run actual OpenCV, ADB subprocess fixtures, and two independent
spawned workers replaying generated recording source. Existing protocol, actual
H.264/PyAV, socket, editor, lifecycle and worker tests continue to run.

Regression coverage also verifies endpoint-exact pairing acknowledgment, code
redaction, recovery from a failed Wi-Fi disconnect, queued capture cancellation
after project changes, and downscaling a template larger than the search image.

Review screenshots show actual Qt widgets with **fixture phones** and synthetic
pixels. They are not screenshots of real Android streaming:

- [Device Manager](screenshots/devices-fixture.png)
- [Screenshot & Visual Tools](screenshots/visual-fixture.png)
- [Action Recorder](screenshots/recorder-fixture.png)

## Source inventory

Created:

- `app/automation/recording.py`: connection/session-bound recorder and Python generation.
- `app/ui/device_manager.py`, `visual_tools.py`, `recorder_panel.py`: modular panels and bounded image helpers.
- `tests/test_network_devices.py`, `test_scaled_recognition.py`, `test_recording.py`,
  `test_visual_library.py`, `test_visual_workspaces.py`, `probe_visual_workspaces.py`.
- This report, `PULL_REQUEST_DEVICE_MANAGER_VISUAL_TOOLS.md`, and the three fixture screenshots above.

Modified:

- `app/ui/window.py`: navigation, panel wiring, background operations, selection,
  capture, recording, connection invalidation and existing run/stop integration.
- `app/ui/capture_dialog.py`: saved-template, scale and search-region match testing.
- `app/devices/adb.py`: validated endpoint management and explicit acknowledgments.
- `app/vision/matching.py`, `app/automation/api/models.py`, `device.py`: optional
  explicit multi-scale recognition with the existing default behavior.
- `app/editor/catalog.py`, `widget.py`: Pattern assistance and editor layout stretch.
- `app/main.py`: current capabilities in diagnostics.
- `tests/test_editor.py`, `test_script_editor.py`: extended existing expectations.
- `README.md`, `README_UBUNTU.md`, `BLUEPRINT.md`, `DEVELOPMENT.md`, `PHASES.md`,
  `SCRIPTING_API.md`, `SCRIPTING_ENGINE.md`, `VALIDATION.md`: usage/status links and contracts.

Dependency manifests, pins, Qt WebChannel restrictions, streaming transport,
worker process architecture and the original product specification remain intact.

## Use this feature branch

To test before merging, from an existing clone:

```bash
git fetch origin feat/device-manager-visual-tools
git switch --track -c feat/device-manager-visual-tools origin/feat/device-manager-visual-tools
```

If the branch already exists locally, switch to it normally. For a new checkout:

```bash
git clone --branch feat/device-manager-visual-tools https://github.com/MD7-1337/Bot_Frm.git
cd Bot_Frm
```

Then follow [Ubuntu 22.04 setup](../README_UBUNTU.md) or the intended Windows
PowerShell commands in [README](../README.md). No new dependency or installer is
required. The source ZIP and any other checkout of main do not acquire these
features until the user chooses to merge this branch.

1. Choose the project root; confirm its images resolve in Visual Tools.
2. Open Device Manager, connect/authorize USB or pair/connect Wi-Fi, and refresh.
3. Select the exact serial, then open the preview and explicitly start live or
   screenshot fallback. Name/group labels never alter transport identity.
4. Capture a region, save in `images/`, select the saved target, adjust settings,
   test on a fresh capture and insert valid Pattern commands into Monaco.
5. Start recording on an idle phone. Use preview controls and Home/Back, pause
   and resume, then stop. Review/edit the timeline and insert Python. Save and
   approve it for the intended phone(s) using normal Run/Execution commands.
6. Keep Emergency stop accessible. Reset explicitly before sending new inputs.

## Limitations and remaining acceptance tasks

No Android hardware was available. USB/Wi-Fi pairing/authentication, actual
scrcpy streaming, physical input, model/codec behavior and disconnection timing
still need real-device validation. Manufacturer, Android version, battery and
charging telemetry are not collected in this increment; unavailable values are
not invented. Wi-Fi mDNS discovery, remote enabling of TCP mode, automatic
reconnection, persistent device task schedules and group-wide app controls remain
future work. Network connection output contracts assume modern Google ADB.

Only Linux x86-64 was exercised. No Windows 10/11 machine, Windows drivers, native
Windows spawn run, clean deployment or high-DPI/monitor acceptance was tested.
The changes use PySide6 and standard Python/subprocess APIs; that preserves the
architecture but does not establish Windows compatibility. No installer was built.

Recorder timelines are session-only until inserted/saved as a script. Timing
uses dispatch timestamps and requested gesture duration; ADB/host latency changes
replay timing. ADB acceptance does not prove app-specific recognition of input.
Only one in-flight manual control per phone is accepted, and actions already sent
cannot be reversed. Recording ordinary Python or editing a call provides no OS
sandbox; replay still requires the existing trust confirmation. Full timeline
image conversion, curved gesture paths and advanced recorder persistence remain.

Explicit scales are bounded to 1–16 finite values in [0.1, 4]. Scaling costs one
correlation search per distinct requested dimension and uses up to the requested
result limit per scale before global suppression. Very small scales can remove
spatial information and yield no candidate. There is no automatic scale search,
OCR, color/pixel API, UI hierarchy recognition or lighting/perspective correction.
Native matching remains cancellable at existing API checkpoints; a running OpenCV
call is not interrupted mid-call. Existing worker termination remains the stop
fallback. Worker isolation/global emergency stop/Monaco QWebChannel are preserved.

Before merging, test on **two real phones**, including one over Wi-Fi:

1. On Ubuntu 22.04 and separately Windows 10/11 x64, record OS, drivers, Python,
   Qt, ADB, scrcpy/PyAV and phone/Android versions. Check authorization/offline/
   disconnected handling and names/groups surviving restart.
2. Verify pairing with the pairing port and connection with the connection port;
   a wrong code/port must report failure. Disconnect only the selected Wi-Fi
   endpoint while the other phone keeps previewing/running. Reconnect explicitly.
3. Run the existing scrcpy rotation/geometry/encoder checklist in STREAMING.md.
   Check two simultaneous previews and input serials at corners and letterboxes.
4. Compare saved PNG dimensions with the original phone resolution while streaming
   at a reduced size. Capture/crop, browse, test unique/absent/ambiguous targets,
   thresholds, offsets, search bounds and multiple explicit scales.
5. Record a workflow, pause/resume, edit/reorder/delete steps, insert/save, replay
   independently on both phones. Inspect actual timing/long press/double tap.
   Disconnect/emergency-stop during a command: no unacknowledged step or stale
   completion may enter a later recording, and no script may auto-resume.
6. Close during discovery, capture, matching, recording and video startup. Verify
   cleanup, responsiveness, saved project/source and no unrelated ADB termination.
