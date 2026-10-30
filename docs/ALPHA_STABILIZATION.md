# Critical alpha stabilization and workspace redesign

Date: 2026-10-30. Branch: `fix/alpha-device-connect-and-ux-overhaul`, stacked on
`feat/device-manager-visual-tools` at `a86c931`. Application source version remains
0.2.0. This is an alpha source increment, not a Windows release or hardware pass.

## What was actually wrong

The user clarified during this assignment: **USB was used, and the connection
problem was on the PC, not the application.** We do not have that computer's
USB/driver/udev diagnostic report or a physical phone in cloud. We therefore
cannot identify the exact host restriction, claim to repair it remotely, or
claim the real connection problem is solved. The UI now exposes the necessary
observations and next steps without requesting privileged host changes.

Confirmed software defects and gaps found by source audit/reproduction:

| Finding | Consequence | Repair/evidence |
| --- | --- | --- |
| ADB's `???????????? no permissions` row failed strict serial validation and was dropped | A real host USB permissions problem could appear as no phone | Preserve the unreadable diagnostic row; never permit it as a command target. Parser, registry and GUI diagnostic regressions pass. Duplicate unreadable identities are coalesced without inventing controllable serials. |
| Open preview only raised a dock | Pressing it did not start the stream and appeared to do nothing | Start or reveal the selected phone's existing StreamManager session. Visible-button journey requires a resulting frame. |
| No GUI-selected ADB path/version/server diagnostic | Users could not distinguish missing downloaded tools, wrong PATH ADB, host access or a video failure | Saved path selection, explicit precedence, staged diagnostics, raw discovery, version and safe server response checks. No silent fallback for an explicitly wrong path. |
| Wi-Fi transport acknowledgment was presented before a verified usable phone | Connection could appear accepted while unauthorized/offline | Rediscover the exact endpoint, require authorized state and a harmless Android query before connected confirmation. Pairing is explicitly separate. |
| An ADB path containing `~` was not expanded | A valid user-local path could fail to execute | Expand explicit user paths; retain explicit missing/nonexecutable paths as actionable errors. |
| Controls were scattered over three toolbars/five competing docks; old layout could hide capabilities | Missing-looking tools, little editor space and poor discoverability | New central workspaces/sidebar, contextual actions, shared preview slots, project tree/tabs, responsive splitters and an always-present stop control. Legacy saved dock state is retained but no longer imposed on the new layout. |
| Insertion could silently do nothing before Monaco loaded; prerequisite states were unclear | Buttons looked nonfunctional | Feedback for unavailable editor operations; enable run/input/capture/recognition/recording controls from actual context and acknowledged run state. |
| A hidden wide page initially constrained the redesigned window | Laptop resizing was blocked at 1203 px | Fix stack sizing and responsive page/preview behavior; actual 1024×700 and 1100×760 checks now pass. Compact properties scroll and previews remain explicitly accessible. |
| Existing tests did not exercise the school PC, Windows or physical Android; several GUI probes invoked controller methods or synthetic hidden-widget events | 569 passing tests did not demonstrate a usable physical-phone journey | Add a visible/enabled-control Qt journey, failure-stage/report tests, actual local ADB evidence, window-size/scaling checks and a clear hardware gate. Keep all older tests and real codec/socket/worker checks. |

Possible cable, host policy, group/udev, Android authorization, Windows OEM driver,
server conflict or school network restrictions remain **environment/hardware
hypotheses until diagnosed on the user's computer**. The app does not bypass
permissions, run sudo, issue `kill-server` or silently enable USB networking.

## Delivered vertical slices

### Connection center

Device Manager now combines cards, actual serial/state/model, selected metadata,
Android version where accessible, saved names/groups, connection history and
USB/Wi-Fi guidance. Discovery is automatic and backgrounded. Existing selection,
connection generations and serial isolation are preserved. Unreadable serials
are diagnostic-only; no fake unique phone identity is generated.

Diagnose Connection covers eight stages: executable/path, version, server,
raw discovery, authorization, harmless Android query, decoded original PNG,
and scrcpy startup/receipt of a real decoded RGB frame. A failure stops later
checks as NOT VERIFIED, with advice. Cancellation waits for an already bounded
subprocess/native operation. Existing previews are observed without taking
ownership; diagnostic-owned streams stop afterward. Copy Report defaults to
serial/home redaction and contains no screen pixels or pairing code. A CLI
counterpart supports collection without Qt Widgets. The GUI remains the primary
workflow; users are not required to diagnose exclusively in a terminal.

Settings supports the effective ADB/server path and explicit precedence:
`STUDIO_ADB` override, saved ADB choice, PATH, then downloaded local tools. Server
selection similarly honors `STUDIO_SCRCPY_SERVER`. No automatic binary/server
replacement is disguised as a successful connection. Stop jobs/previews/runs
before changing tools; a missing explicit path stays an explicit diagnostic error.

### Workspace experience

This is a structural UI redesign, not just a color change. Sidebar navigation
switches actual central workspaces: Script Studio, Device Manager, Visual Tools,
Recorder, Activity & Logs, Task Manager and Settings. Script Studio has up to 20
host-owned script buffers, a bounded background project explorer, Monaco as the
focus, an optional phone pane and bottom execution/output. Device selection and
emergency stopping remain in the header across workspaces. Native command search
uses the existing enabled QActions; no execution/device slot was added to the
web bridge. The two host command shortcuts are registered using native Qt actions.

Reusable design tokens provide original vector icons, consistent typography,
spacing, focus/hover/disabled states, surfaces and light/dark themes. Appearance
also applies to the actual Monaco instance. Splitters and the last workspace
persist under versioned settings; the older dock-layout setting is left intact.
At compact sizes the sidebar collapses, the project tree makes room for the
editor and Preview explicitly reveals the phone. Properties scroll when needed.
Qt's normal high-DPI behavior is preserved; real Windows/monitor acceptance is
still open. The application does not present synthetic phones during normal use.

### Capture, script and recorder integration

The existing full-resolution screenshot/crop/Android coordinate and fresh OpenCV
comparison implementation remains. A central library and target inspector expose
Pattern threshold, region, offset and explicit scales, valid Python insertion and
fresh testing. Shared preview controls now include Home, Back and Capture. Video
transport, PyAV decoding, frame stores and device-specific input adapters were
preserved. No screenshot is substituted for streaming.

The existing trusted spawned-worker path still runs shared or distinct scripts,
reports output/errors/lines and handles pause/resume/stop and device generations.
Tabs preserve unsaved source, select an already-open file without replacing its
buffer, and prompt about unsaved documents on close. Workers still execute approved
source snapshots rather than arbitrary scripts on the GUI thread.

Recorder adds bounded versioned JSON save/open, transactional validation, editable
calls, explicit delays and a Replay button using normal trusted worker execution.
Loading never runs a call, reconnects the stored serial or adopts an old generation.
Only completed studio controls for the recorded context are captured. A failed,
disconnected or obsolete action never becomes a successful recorded step. Pause,
emergency stop and already-sent-input limitations remain unchanged.

### Feasible recognition and platform continuation

`getPixel(x, y)` returns RGB from a fresh original-resolution screen.
`findColor((r,g,b), tolerance=0, region=None, limit=100)` returns row-major original
pixel locations with inclusive per-channel tolerance; results are pixels, not
clustered objects. Both scripting styles bind to their own device context and are
included in Monaco assistance. Real arrays and two independent spawned scripts
exercise these commands. Explicit multi-scale template matching remains in use.

Parent-process CPU and resident-memory observations are shown where available;
worker/WebEngine child totals are not claimed. Windows has a standard-library
adapter and a new source/GUI CI job; its execution has not been observed here.
Linux and PowerShell launchers and a no-sudo user guide were added. No installer,
updater, OCR, debugger, scheduler or automatic recovery engine was added. Task
Manager explicitly describes unimplemented scheduling and links to real current
script assignments; it cannot produce a fake task.

## Validation obtained

**Final full suite: 620 passed, 0 failed, 0 skipped; exit 0; 32.68 seconds.**
The older 569 tests remain; existing Qt subprocess wrappers now use `STUDIO_CONFIG_DIR` to isolate
configuration on Windows as well as Linux. Fixture adapters were extended for
new harmless queries rather than weakening routing or lifecycle assertions.

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu \
STUDIO_CONFIG_DIR=/tmp/aas-alpha-final-regression .venv/bin/python -m pytest -q
```

The complete visible-control probe also passed separately at
`QT_SCALE_FACTOR=1.25`. These are actual headless Qt logical-size/scaling checks,
not physical Windows monitor validation. The current report includes 51 additional
collected cases beyond the previous 569, including generated API-contract cases.

The new visible-control journey checks:

- absent-device disabled state and a permission-denied diagnostic, redacted clipboard report;
- actual visible Pair/Connect/Disconnect controls with separate ports and no code in logs;
- unauthorized transport is not reported as a usable phone;
- preview start, mapped tap, native screenshot selection/crop/save/reference and fresh match;
- real Monaco source save and actual spawned worker run, pause, resume and stop;
- recorder capture, delay, save/open without execution, and real worker replay;
- unsaved tabs, actual light/dark/Monaco font changes and native command search;
- guarded tool changes and a real AdbClient rebind to a missing executable with failed diagnostics;
- 1440×900, 1100×760 and 1024×700 logical window sizes, plus a separate 125% scaling journey;
- cleanup and return to usable Qt state.

All phone/screens in this GUI journey are explicit fixtures; worker, editor,
OpenCV and native Qt behavior are real. Existing actual H.264/PyAV/socket and
multi-phone worker tests remain. This distinction is essential: simulated Android
transport does not become physical Android validation because other parts are real.

Actual local ADB invocation: executable/version/server/discovery pass and discovery
returns no phone. Authorization fails with **No device detected**; query/capture/
video are NOT VERIFIED. See the committed [actual cloud connection report](validation/alpha-cloud-connection.txt).
The CLI exits 1 for this expected no-phone diagnostic, not an application crash.

`compileall`, launcher `--diagnostics` and diff whitespace checks pass. Headless
GUI tests used the cloud platform's supported escalated IPC execution and isolated
browser flags. Normal desktop startup keeps the browser sandbox enabled.

Platform exercised: Linux x86-64, kernel 6.18.55/glibc 2.41; Python 3.12.14,
PySide6 6.8.3, Monaco 0.52.2, NumPy 2.2.4, OpenCV-headless 4.11.0.86,
PyAV 14.2.0, pytest 8.3.5. This is not Ubuntu 22.04 or Windows acceptance.

### GUI evidence

Actual rendered Qt widgets, all clearly marked **FIXTURE / no Android hardware**:

| Workspace | Screenshot |
| --- | --- |
| Script Studio | [Desktop](screenshots/alpha/alpha-studio.png), [1024×700](screenshots/alpha/alpha-compact.png) |
| Device Manager | [Desktop](screenshots/alpha/alpha-devices.png), [1024×700](screenshots/alpha/alpha-devices-compact.png) |
| Connection diagnostics | [Stages/report](screenshots/alpha/alpha-diagnostics.png) |
| Phone preview | [Fixture screen](screenshots/alpha/alpha-preview.png) |
| Visual Tools | [Desktop](screenshots/alpha/alpha-visual.png), [1024×700](screenshots/alpha/alpha-visual-compact.png) |
| Recorder | [Desktop](screenshots/alpha/alpha-recorder.png), [1024×700](screenshots/alpha/alpha-recorder-compact.png) |
| Settings | [Desktop](screenshots/alpha/alpha-settings.png), [1024×700](screenshots/alpha/alpha-settings-compact.png) |
| Activity & Logs | [Metrics/runs](screenshots/alpha/alpha-monitor.png) |

The rendered images were inspected and iterated for editor space, empty states,
readable controls, disabled primary actions, native shortcut behavior, compact
accessibility and scrollable target properties. Synthetic content is not Android
streaming evidence. Visual quality on Windows fonts/themes/monitors still needs
user review.

## What is NOT VERIFIED or remains next

- Actual USB/Wi-Fi authorization, screenshot, scrcpy codec/input, recording timing,
  disconnect/reconnect behavior and two real-phone workflows. No phone was attached.
- Exact restriction on the user's school PC. The user identified the PC as the
  problem; collect its redacted GUI diagnostic and involve IT if permissions apply.
- Windows 10/11 runtime, USB drivers, real high-DPI/multi-monitor changes, native
  deployment and installer. Windows CI is configured, not a witnessed pass.
- OCR/text/UI hierarchy recognition, full debugger, scheduler/recovery, richer
  process/device telemetry, recorder image conversion/curved multitouch and Windows
  packaging. They were deferred to protect the coherent stabilization milestones.
- Session timings approximate dispatch gaps and requested durations; app/ADB latency
  changes replay behavior. Recorded coordinates are not automatically rescaled.
- Native calls are bounded but not all interruptible mid-call; already dispatched
  phone actions cannot be undone. Trusted Python retains host-user permissions.
- Serial/model metadata can be unavailable; discovery does not invent missing values.
  Multiple unreadable permission-denied USB identities cannot be distinguished until
  the host exposes real serials. No GUI can repair a driver/udev policy by itself.
- No application command issues `kill-server`. Google ADB can itself restart a
  version-incompatible server; choose the intended matching SDK tools explicitly.

Use [LOCAL_TESTING.md](LOCAL_TESTING.md) for beginner startup/phone/diagnostic/capture/
script/recorder instructions and the explicit real-device checklist. The complete
[control inventory](CONTROL_INVENTORY.md) classifies actual functionality and limits.

## Source inventory

New application modules: `app/devices/diagnostics.py`, `app/settings.py`,
`app/host_metrics.py`, `app/vision/color.py`, `app/ui/components.py`, `design.py`,
`shell.py`, `script_studio.py`, `settings_panel.py`.

Modified application modules: `app/devices/adb.py`, `paths.py`, `registry.py`,
`app/ui/window.py`, `device_manager.py`, `live_panel.py`, `visual_tools.py`,
`recorder_panel.py`, `app/automation/recording.py`, `api/device.py`,
`app/editor/widget.py`, `app/main.py`, `editor_web/editor.js`.

New verification/startup: `tests/test_connection_diagnostics.py`,
`test_alpha_features.py`, `test_alpha_ux.py`, `probe_alpha_ux.py`,
`tools/run-studio.sh`, `run-studio.ps1`, `.github/workflows/alpha-tests.yml`.

Modified test support: `tests/probe_device_workbench.py` and GUI subprocess
wrappers in `test_capture_dialog.py`, `test_device_workbench.py`, `test_editor.py`,
`test_preview_live.py`, `test_script_project_ui.py`, `test_script_workbench.py`,
`test_ui_safety.py`, `test_visual_workspaces.py`.

Documentation: this report, `CONTROL_INVENTORY.md`, `LOCAL_TESTING.md`,
`PULL_REQUEST_ALPHA_STABILIZATION.md`, the actual cloud diagnostic text, 13 fixture
screenshots and current README/API/architecture/phase/development links.
Dependency manifests/lock pins, original specification, low-level streaming/decoder
and worker process implementation were preserved.

## Delivery and review boundary

This work belongs only to `fix/alpha-device-connect-and-ux-overhaul`, with a draft
PR targeting **feat/device-manager-visual-tools**, not main. Neither branch is
merged automatically. No force push, branch deletion or protection change is
part of delivery. The final Git report supplies the actual commit/push/PR result;
[PULL_REQUEST_ALPHA_STABILIZATION.md](PULL_REQUEST_ALPHA_STABILIZATION.md) contains
a ready review description if API access prevents creation. User review and
real-device acceptance remain necessary before deciding to merge.
