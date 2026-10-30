# Development and release runbook

The current scripting contract and test report are in
[SCRIPTING_API.md](SCRIPTING_API.md) and [SCRIPTING_ENGINE.md](SCRIPTING_ENGINE.md).
`app/automation/api` owns public targets/errors/commands and context-local
functions; `backends.py` owns serial-bound adapters; `app/projects/library.py`
owns shared path containment; `app/editor/catalog.py` derives editor assistance
from the real API. Keep these boundaries when adding commands.

Current device/video/capture instructions and the exact source inventory are in
[DEVICE_INTEGRATION.md](DEVICE_INTEGRATION.md); scrcpy wire assumptions and
cleanup are in [STREAMING.md](STREAMING.md). The Phase 0 history remains below.

## Source map

| Path | Responsibility |
| --- | --- |
| `app/main.py` | CLI, dependency diagnostics, Qt bootstrap |
| `app/ui/window.py`, `preview.py` | Dock workbench, user approval, asynchronous UI operations, screenshot rendering/input |
| `app/editor/bridge.py`, `widget.py` | Restricted editor bridge, syntax analysis, isolated local WebEngine profile |
| `editor_web/` | Local HTML/CSS/JS integration; generated integrity-checked Monaco in `vendor/` |
| `app/devices/` | Validated serial-specific ADB process boundary and executable selection |
| `app/streaming/` | Coordinate math, latest immutable PNG captures, managed external scrcpy fallback |
| `app/automation/runtime.py` | Spawn workers, run-local API, JSON events, leases, trust gate, bounded cancellation |
| `app/automation/qt_service.py` | Dedicated coordinator owner thread and bounded Qt command frontend |
| `app/vision/matching.py` | Actual OpenCV recognition and typed immutable match geometry |
| `tools/` | Verified dependency acquisition, reusable cloud setup, real editor probe |
| `tests/` | Deterministic unit/process tests and opt-in real GUI integrations |
| `examples/two_devices.py` | Two genuinely spawned mock-device runs |

Use the existing isolated checkout. Do not create a Git worktree for routine cloud tasks. Preserve user changes. This initial repository had no files or commits; all implementation files were created locally, with no push or publication performed.

## Contribution workflow

Read the blueprint before changing subsystem boundaries. Keep blocking ADB, matching, disk-heavy project work and worker lifecycle operations off the GUI thread. Never add a device-targeted ADB operation without `-s`. Use argv lists; never interpolate remote-shell input. ADB key/touch parameters have strict validation.

Use `uv sync --locked --extra test`, run relevant tests, then run the complete suite before merging interface changes. Update the validation report when behavior or evidence changes. Keep the lockfile and vendored-resource integrity pins deliberate. Do not introduce runtime Node, a replacement web frontend, or unsafe bridge execution.

Tests use fixtures to cover errors consistently. Keep hardware tests explicitly opt-in, identify fixture backends in output, and record actual device/platform versions when hardware becomes available. QtCore service tests run in the main test process; WebEngine tests run in child processes so they cannot contaminate Qt application lifecycles.

## Troubleshooting

The current UI changes, recorder contracts, evidence and real-device checklist
are in [DEVICE_MANAGER_VISUAL_TOOLS.md](DEVICE_MANAGER_VISUAL_TOOLS.md).
Use Workspaces (`Ctrl+1`–`Ctrl+4`) to reopen hidden tools, or View → Reset layout.
Wi-Fi connection management uses explicit host:port arguments without `-s`;
screen/input/application operations continue to require an exact serial.

| Symptom | Diagnosis/action |
| --- | --- |
| Monaco assets missing | Run `python tools/fetch_monaco.py` using the environment Python. Keep its digest check enabled. |
| Qt platform/plugin error on desktop | Check supported OS, graphics drivers, architecture, and Qt runtime libraries. Do not mix OpenCV GUI Qt plugins with PySide6. |
| Chromium local IPC denied in cloud | Run the documented integration test outside the command sandbox; preserve normal browser sandboxing on desktop. |
| `adb` unavailable | Run verified development tool download or configure `STUDIO_ADB`; use diagnostics to see resolved executable. |
| No phones | Check physical USB passthrough, cable, authorization and Windows driver. This Linux cloud instance reported zero devices. |
| `unauthorized` / `offline` | Unlock the phone and approve debugging; resolve transport health before retrying. Never report connected metadata that was not read. |
| Worker start rejected | Approve trusted execution, use an available serial and observe worker limits/device lease. Reset a latched emergency stop explicitly. |
| Recognition rejects template | Use RGB `uint8` arrays with nonconstant channels/texture, supported dimensions, finite score threshold, and a valid search region. |
| scrcpy missing | Screenshot fallback remains available. Configure a compatible scrcpy executable before testing the external adapter. No decoder implementation is hidden behind it. |
| Window waits on close | Owned workers and ADB jobs must finish/stop; the UI defers close rather than destroy a running service. ADB operations have finite timeouts. |

## Hardware continuation

Phase 0 cannot establish the two-phone or Windows gates without their platforms. With two authorized phones on Windows x64, record ADB/scrcpy/server/decoder versions, phone models/Android versions, USB/Wi-Fi transport, actual resolution/orientation and observed results. Test discovery, screen decode/render, mapped input at corners/letterboxes, disconnection, independently progressing runs and cleanup.

The pinned video-only scrcpy client and H.264 decoder are now implemented and fixture-tested. The next gate is actual Android server/codec/input validation, including metadata and reconfiguration on hardware. Keep the existing screenshot and external-window fallbacks visibly labeled until hardware streaming passes. The protocol control socket remains disabled; input uses validated ADB. Details and exact hardware steps are in `STREAMING.md` and `DEVICE_INTEGRATION.md`.

## Packaging evaluation and release gates

No executable or installer is delivered in Phase 0. Plan a Windows-built PyInstaller directory payload, followed by Inno Setup and a portable ZIP of the same tested payload. Explicitly include editor HTML/JS/CSS/Monaco notices, QtWebEngineProcess, resources, locales, plugins, Python runtime and approved native tool dependencies. Resolve resource paths for a frozen application before writing a release spec; the current paths target source development.

Inspect the exact Qt/Chromium, ADB, scrcpy/SDL/FFmpeg, OCR models, Python and scientific-wheel licenses. The project itself has no release license selected yet. Generate a dependency bill of materials and bundled notices before redistribution. Code signing and authenticated update metadata are later release prerequisites; no unsigned update mechanism is provided now.

The release gate requires clean Windows 10/11 x64 machines without Python/Node, offline editor use, real two-phone control/run scenarios, DPI/monitor transitions, GPU fallback, process cleanup, installer/uninstaller, portable ZIP, upgrade/project preservation and corrupt-update rejection. Do not call a Linux source smoke test a Windows packaging test.
