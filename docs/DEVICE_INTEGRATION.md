# Device preview, control and visual capture — implementation report

Historical stage report. The subsequent foundational scripting engine is
implemented and reported in [SCRIPTING_ENGINE.md](SCRIPTING_ENGINE.md), with its
executable contract in [SCRIPTING_API.md](SCRIPTING_API.md). Statements below
about image `click()` being future work describe the earlier stage only.

Date: 2026-10-29. This increment extends the existing Phase 0 application;
it does not replace its Python/PySide6 architecture, editor or worker model.
**The backend and GUI are implemented and fixture-tested. No physical Android
device or Windows machine was available, so those acceptance gates remain open.**

## Implemented behavior

### ADB and independent device state

Discovery preserves actual serial identity and distinguishes device, offline,
unauthorized, no-permissions, disconnected and unknown observations. Successful
absence marks a known serial disconnected; failed discovery marks it unknown,
not falsely absent. The device list preserves the selected identity when that
phone disappears, rather than redirect controls to another phone.

Every target operation supplies `-s SERIAL`. Full PNG dimensions establish
current Android coordinate size. Optional `dumpsys input` metadata supplies
observed rotation; unsupported metadata stays unavailable. Validated tap,
double tap, stationary long press, swipe/drag and key input run off the GUI
thread. Errors distinguish authorization, offline/permission and transport faults.

Connection generations and cancellation tokens invalidate queued manual input,
pending/active workers and streams belonging to a lost connection. A worker
activation gate rechecks the connection after spawning, so a start approved on
an old connection cannot execute merely because the device later reconnects.
Loss of one phone does not stop other phones. Resumption requires a fresh user
start; old input/source is not replayed.

### Embedded live video

The primary backend uses the exact checksum-verified **scrcpy server 3.1** with
video-only H.264 over its own serial-specific ADB forward. PyAV 14.2.0 performs
actual decoding in a background thread. Each phone has an independent socket,
decoder, latest-frame mailbox, original geometry, status and cleanup lifecycle.
Qt paints packed RGB directly, without using screenshot polling to simulate video.

The preview panel supports selected-device live view plus independent tiles,
explicit start/stop/all-connected actions and FPS/bitrate/maximum-size controls.
The default concurrency cap is four. The UI exposes 1–60 FPS, 1–32 Mbit/s and
256–4096 px; the backend validates a wider encoder-option range. Settings apply
at start, so changing an active stream requires stopping and starting it.
These are encoder requests, not observed performance promises.

Only the latest frame is retained. A 33 ms GUI timer renders new frames without
running ADB or decoding on the Qt thread. Original Android dimensions are kept
separate from scaled video dimensions. Aspect-preserving fit rejects letterboxes;
source size/orientation changes cancel obsolete gestures. Source geometry is
rechecked in the background initially, on encoded-size changes and at two-second
checkpoints while frames arrive, including same-aspect size changes and 180° turns.

Startup metadata/first decoded frame and partial packets have bounded deadlines.
An established unchanged screen may legitimately send no packets. Stop clears
the latest frame immediately, wakes socket reads and cleans only the owned
local shell child, forward, socket and generated remote JAR. Errors stay visible.
The existing external scrcpy adapter remains available as a backend fallback;
the embedded path requires only the Android server, not a native scrcpy GUI.
The explicitly labeled ADB screenshot fallback remains selectable.

The verified upstream sources, packet layout, server argv, digest, assumptions
and lifecycle are documented in [STREAMING.md](STREAMING.md).

### Interaction and capture-to-code

Single taps wait through Qt's double-click interval; a double tap produces two
serial-specific inputs without an accidental third tap. Held gestures map to
stationary long press; drags/swipes map endpoints and duration to Android input.
Home/Back target the selected row. Background preview gestures target their own
phone even while another row is selected. Manual input is blocked while that
phone's worker owns it. Emergency stop invalidates deferred and queued gestures
and latches further input until explicit reset.

**Capture image region…** (`Ctrl+Shift+C`) freezes a fresh original-resolution
PNG from the selected phone while live video continues. The dialog lets users:

1. Drag a rectangle and inspect its Android bounds.
2. Crop and atomically save PNG pixels, with file-dialog overwrite confirmation.
3. Insert an ordinary safely quoted `image_path = "..."` reference into Monaco.
4. Test the selected template against a fresh capture of that same phone.
5. Inspect match scores, rectangles and computed Android tap positions, including
   no-match, invalid/constant-template, ambiguity and changed-resolution errors.

The frozen crop and fresh comparison use separate images, so overlays do not
alter saved pixels. Matching/capture runs off the UI thread. Relative references
are generated when the script has a directory; otherwise the explicit absolute
path is used. A changed editor document is not silently given a reference
relative to the old document. The generated assignment is runnable under the
current subset; full image `click()` and project asset-library APIs remain later
work. Test Match never sends input or treats scores as probabilities.

## Actual validation

Final command, from `/workspace/Bot_Frm`:

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu' \
XDG_CONFIG_HOME=/tmp/aas-device-tests .venv/bin/python -m pytest -q
```

**259 passed, 0 failed, 0 skipped; exit 0; 15.03 seconds.** All original test
cases remain present. The existing UI probe now registers explicit fixture
devices and waits for the intentional single/double-tap distinction. No device
assertions were removed or turned into fake success results.

| Validation | Evidence actually obtained |
| --- | --- |
| Existing application/runtime/editor/vision | Preserved regression suite passed, including actual local Monaco and WebChannel behavior. |
| ADB | Mocked multi-device argv, states, generations, geometry, errors and input validation passed. Actual installed ADB 37.0.1 version/discovery succeeded with zero devices. |
| Video wire contract | Fragmented metadata/packet reads, codec/length limits, cancellation, bounded first frame, config-only startup, partial timeout, EOF and legitimate established idle passed. |
| Actual video decoding | Real FFmpeg/libx264-generated H.264 was decoded by PyAV, including codec configuration, RGB output and resolution changes. |
| Full session fixture | Real local socket pairs delivered fragmented scrcpy packets through transport/parser/decoder. Tests checked original dimensions, 180° metadata, disconnect, handshake cancellation and owned-resource cleanup. Android server/ADB results in these cases are fixtures. |
| Multi-stream manager | Independent serial mailboxes, latest-only replacement, caps, failure isolation, stop invalidation and restart/cleanup gating passed. |
| Real Qt preview | Actual QImage RGB pixels, scaled source transforms, all rotations, letterboxes, single/double tap, long press/swipe, input invalidation and overlays passed with synthetic images/events. |
| Capture workflow | Real mouse rectangle selection, crop pixel checks, Unicode/quoted filename PNG save, inert Python references, fresh OpenCV matching, ambiguity/no-match, responsive timer and deferred-close tests passed. |
| Integrated workbench | Real Qt + Monaco displayed two injected fixture sources, routed a background tile to its own serial, saved/cropped/inserted a reference, matched a fresh image and disconnected one phone without affecting the other or redirecting selection. |
| Device-loss worker races | Actual spawned workers verified stale queued start rejection, pre-execution activation gating, per-phone cancellation, surviving second worker and fresh explicit restart. |
| Setup/dependencies | Updated `bash tools/setup.sh` completed end to end. PyAV installed with the locked environment; official server SHA-256 matched and repeat setup reused the verified server. Diagnostics report expected versions/paths; package compatibility and source compilation passed. |

The command sandbox restricts local IPC, so the full suite used its supported
escalated execution mode. Browser sandbox disabling is limited to this isolated
headless test configuration; normal desktop startup does not set it. Headless
GPU/Vulkan warnings did not prevent the actual behavioral checks from passing.

Two early integrated-probe failures were test-harness issues: input was injected
before Qt finished laying out new tiles (which correctly invalidates an obsolete
gesture), and the probe compared escaped Python source instead of its Unicode
literal value. The corrected probe settles layout and checks the parsed Python
value; the final full run above passed. There are no unresolved automated failures.

**Operating system tested:** Linux x86-64, kernel 6.18.55, glibc 2.41, headless.
Python 3.12.14; Qt/PySide6 6.8.3; Monaco 0.52.2; PyAV 14.2.0;
NumPy 2.2.4; OpenCV-headless 4.11.0.86; pytest 8.3.5.
Windows 10/11 is the target, not a platform verified by these Linux results.

## Files created

| Area | New files |
| --- | --- |
| Device state | `app/devices/registry.py` |
| Streaming | `app/streaming/protocol.py`, `decoder.py`, `session.py`, `manager.py` |
| Capture/assets | `app/ui/capture_dialog.py`, `live_panel.py`, `app/projects/__init__.py`, `assets.py` |
| Provisioning | `tools/fetch_scrcpy.py` |
| Tests | `tests/test_device_integration.py`, `test_stream_protocol.py`, `test_stream_decoder.py`, `test_stream_session.py`, `test_stream_manager.py`, `test_preview_live.py`, `probe_preview_live.py`, `test_capture_assets.py`, `test_capture_dialog.py`, `probe_capture_dialog.py`, `test_service_device_loss.py`, `test_device_workbench.py`, `probe_device_workbench.py` |
| Documentation | `docs/PRODUCT_SPEC.md` (stable link to existing specification), `STREAMING.md`, `DEVICE_INTEGRATION.md` |

## Existing files modified

- `app/devices/adb.py`: state/error/geometry/input stabilization.
- `app/automation/runtime.py`, `qt_service.py`: device-generation invalidation and worker activation/cancellation gates.
- `app/ui/preview.py`: direct RGB rendering, source geometry, gestures and overlays.
- `app/ui/window.py`: discovery/state lifecycle, multi-preview controls, capture/editor integration and asynchronous cleanup.
- `app/main.py`: current-stage diagnostics including PyAV/server verification.
- `pyproject.toml`, `uv.lock`: pinned PyAV dependency and development version 0.1.0.
- `tools/setup.sh`: verified scrcpy server provisioning.
- `tests/probe_ui_safety.py`: preserve its assertions with verified fixture devices and delayed-tap semantics.
- `README.md`, `docs/BLUEPRINT.md`, `DECISIONS.md`, `PHASES.md`, `DEVELOPMENT.md`, `VALIDATION.md`: current instructions and clearly historical baseline.

No Windows installer was created. No unrelated debugger, recorder, OCR, scheduler,
updater or full scripting API was added. No Git commit, push or environment
publication was performed.

Reusable cloud `install_script` and `start_skill` fields were updated and their
draft save was confirmed. No network domains, secrets or repository membership
were changed. Review and save the configuration in environment settings, then
publish to retain the updated snapshot. A draft save does not establish
publication or successful restoration in a new task.

## Known limitations and unverified gates

- No actual Android server launch, device MediaCodec compatibility, screen/input,
  protected-content behavior, USB permissions, or two-physical-phone test ran.
- Windows startup, QtWebEngine deployment, drivers, DPI/monitor behavior and
  packaging remain unverified. No installer or portable executable is delivered.
- Only the exact server 3.1 / H.264 / default-display / video-only contract is
  supported. Audio and scrcpy's control channel are disabled; input uses ADB.
- ADB gestures are dispatched after mouse release as bounded input commands.
  This is not raw continuous multitouch or physical-touch recording. Android/apps
  may interpret double tap/long press/drag differently.
- Geometry checks occur at observed boundaries and periodic checkpoints, with
  transport latency. Display state and later ADB input cannot be atomic. Device
  discovery polls every three seconds; brief reconnects between observations may
  not be seen. Already-dispatched input cannot be reversed.
- A preview frame older than three seconds is rejected for input. Some encoders
  may not repeat static frames as requested; obtain a fresh screenshot or restart
  before input in that case. No automatic recovery replays actions.
- No hardware FPS/latency, sustained-load or device-count benchmark is claimed.
  Stop/close waits asynchronously for bounded ADB cleanup; removal of a remote
  file cannot succeed while the phone is absent. Cleanup errors remain visible.
- Trusted scripts retain host-user permissions and can bypass built-in adapters.
  This is not a Python sandbox or host-wide ADB exclusion mechanism.

## Exact next steps on real Android devices

1. On a Windows x64 development machine or Linux desktop, install Python 3.12/uv,
   run `uv sync --locked --extra test`, then the three helpers `fetch_monaco.py`,
   `fetch_adb.py` and `fetch_scrcpy.py` with the environment's Python. Windows
   commands are in README.md; their execution is not claimed here.
2. Enable USB debugging on two authorized phones, connect them, approve prompts
   and install required Windows USB drivers. Run `adb devices -l` with the actual
   configured executable; record both serials/models/Android versions.
3. Launch `python -m app.main` using the environment Python. Refresh devices.
   Select phone 1 and Start live, then start phone 2. Verify independently changing
   real screen content. Record server/decoder versions and any encoder errors.
4. Test tap/double tap/hold/drag, Home/Back, letterbox rejection and corner/center
   coordinates on both previews. Scale video with max-size settings and repeat.
5. Rotate each phone through 0/90/180/270°, change resolution (including same
   aspect ratio), and verify remapping/cancellation. Change FPS/quality with
   explicit restart; measure actual behavior rather than assume requested rates.
6. Capture an original-resolution frame, draw/crop/save a target, inspect its
   Python reference and Test Match against a fresh frame. Check ambiguity,
   missing target and rotation/resolution changes while the dialog is open.
7. Run simple trusted scripts independently, then disconnect one phone during
   startup, streaming and execution. Confirm only its work is cancelled, its
   preview clears and selection does not move. Reconnect and explicitly start
   again; confirm nothing from its old connection is replayed.
8. Test emergency stop during gestures, queued starts and active workers; reset
   explicitly. Stop/start streams repeatedly and close during active capture.
   Inspect owned forwarding/server cleanup without killing unrelated sessions.
9. Record actual OS/driver/device/encoder results and measured limitations before
   closing the hardware gate. Repeat the supported Windows matrix separately.
