# Foundational scripting engine — implementation and validation

Latest alpha: [ALPHA_STABILIZATION.md](ALPHA_STABILIZATION.md) adds diagnostics,
workspace integration, recorder JSON sessions and bound RGB APIs. Reports below
remain historical evidence for their own source stages.

Subsequent increment: [Device Manager and Visual Tools](DEVICE_MANAGER_VISUAL_TOOLS.md)
adds explicit multi-scale Pattern matching and a studio-control recorder. The
496-test report below remains the historical scripting-engine stage record.

Date: 2026-10-30. Source development version: 0.2.0. This increment implements
the requested SikuliX-style Python foundation on the existing Qt/Monaco,
ADB/video, capture and spawned-worker architecture. It does not claim completion
of the larger IDE or hardware/Windows acceptance.

The final request ended at “Sc” in the error-handling list. That was treated as
script-error reporting; normal syntax/runtime errors, source locations and
tracebacks are implemented alongside the explicitly listed image/device errors.

## Delivered functionality

- All requested touch, image recognition, timing, Android and screen functions,
  plus explicit `waitImage` and compatible serial-returning `getDevice`.
- One shared implementation for context-local short functions and bound
  `device` methods. No mutable global current-device selector.
- Immutable Pattern/Offset/Region/Location/Match/Screen objects, score thresholds,
  target offsets, contained search regions and multiple-result matching.
- Project image resolution shared with editor previews: image-library precedence,
  relative/script paths, size/format limits and canonical containment.
- Normal Python execution in actual worker processes, including imports,
  conditions, loops, functions, classes, main guards, annotation-aware dataclasses
  and exception handling. Source buffers and globals stay independent per run.
- Shared editor source on selected phones, different assigned files on selected
  phones, per-run table/status, stdout/stderr, typed errors and exact-buffer
  tracebacks. Trust approval remains host-owned.
- Nonblocking GUI run/pause/resume/stop, worker safe-point acknowledgments,
  coalesced current-line reporting, preserved emergency stop and device-generation
  activation/cancellation gates.
- Monaco completion, signatures and docs derived from the real API; actual
  rendered image hover thumbnails, missing-image markers and execution lines.
  Edits clear stale execution highlighting and remain ordinary valid Python.
- Capture saves default to the current project's images directory and inserts
  an ordinary image-path assignment followed by implemented `click(image_path)`.
- Supported Android application/text commands use strict argv validation and
  reject Android error output even when process exit status is zero. Text action
  logs retain count rather than plaintext; long scripting gestures extend and
  restore their own serial-bound transport deadline.

The exact signatures, returns, supported text, exceptions and timing semantics
are in [SCRIPTING_API.md](SCRIPTING_API.md).

## Validation actually obtained

Final command, from `/workspace/Bot_Frm`:

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu' \
XDG_CONFIG_HOME=/tmp/aas-engine-tests .venv/bin/python -m pytest -q
```

**496 passed, 0 failed, 0 skipped; exit 0; 21.51 seconds.** The earlier 259 tests
remain present. Existing GUI fixture stubs were extended for the editor's new
host hooks, and the capture workflow fixture explicitly selects its project.
Assertions were preserved; no hardware tests were substituted with fake results.

| Capability | Evidence |
| --- | --- |
| Foundational API | Actual OpenCV on PNG/RGB fixtures verifies unique/multiple/no matches, regions, offsets, immutable pixels, missing/corrupt assets, invalid parameters and cross-device Match rejection. |
| Timing/cancellation | Appearance/disappearance sequences, zero timeout, positive deadline overrun, paused deadline, cancellation, ambiguity and device failures have distinct tested outcomes. |
| Backend boundary | Mocked subprocess tests verify serial targeting, typed error mapping, launcher/installed-package checks, Android zero-exit failures, supported ASCII input, injection rejection and gesture-deadline restoration. These are not physical Android confirmations. |
| Project paths | Tests cover image-library precedence, nested/scripts paths, explicit project selection, contained absolute paths, traversal/symlink escapes, size/type limits and project discovery. |
| Actual worker processes | Image-based actions execute in separately spawned workers; imported short functions retain the assigned context; normal Python and project imports run; failures/variables/logs remain independent. |
| Run lifecycle | Pause/resume acknowledgments, busy Python, cancellation, native forced-stop fallback, connection-generation invalidation and source/IPC bounds pass. Queued terminal-state events cannot revive a cancelled run. |
| Main-module/source fidelity | Regressions verify `if __name__ == '__main__'`, `from __main__` imports, future-annotation dataclasses and traceback source matching unsaved executed buffers. |
| Current line | A bounded latest-line reporter updates a blocked `sleep()` line rather than keeping an older throttled line; paused location and rapid-loop coalescing are tested. |
| Actual Monaco/Qt | Real WebEngine probes verify API metadata, `device.` completion, signature help, ordinary source, missing markers and execution decorations. The image hover is shown through Monaco and its actual DOM image loads with 40×30 natural dimensions. |
| Read-only preview boundary | Project containment, pixel/file/output limits, remote/file request restrictions and raster-only thumbnail decoding are tested. No execution/device/root-selection slot is exposed. |
| Integrated GUI + workers | Real Monaco and Qt drive two spawned fixture workers, shared source, independent assigned files, pause/resume/stop, line decorations, missing-asset failure and surviving second-phone completion. |
| GUI error paths | Explicit project context survives opening a nested script; failed library validation preserves previous context; Save reports errors without escaping Qt shutdown callbacks. |
| Preserved features | The full device, coordinate, streaming protocol/H.264/local-socket, capture and old runtime/editor suites pass together. |

Additional operations completed:

- `uv lock --offline` and `uv sync --locked --extra test --offline` updated and
  installed the project version without adding dependencies or disabling artifact
  verification. All dependency versions remain pinned.
- `uv pip check` reported installed packages compatible.
- `python -m compileall -q app examples tools tests` completed successfully.
- `python -m examples.run_visual_fixture` generated project PNGs and completed
  both scripting styles in independent spawned workers. The offset simple target
  tapped `(51, 40)` and the explicit-device target `(50, 40)`, exactly as the
  fixture defines. No Android input was sent.
- Diagnostics list all 22 commands, pause/resume availability and the verified
  existing scrcpy 3.1 server. No installer was built.

Headless GUI/socket/process tests used the cloud platform's supported escalated
execution because its command sandbox restricts local IPC. Browser sandbox
disabling is only for this isolated headless test setup, never normal desktop
startup. Headless graphics warnings did not prevent the behavioral assertions.

Review caught and fixed main-guard handling, throttled stale source lines,
nontransactional project selection, nested explicit-root precedence, Save error
handling and long-gesture deadlines. There are no unresolved automated failures
in the final run above. These results do not imply a general Python sandbox or
a clean-Windows acceptance pass.

**Platform exercised:** Linux x86-64, kernel 6.18.55/glibc 2.41; Python 3.12.14,
PySide6 6.8.3, Monaco 0.52.2, NumPy 2.2.4, OpenCV-headless 4.11.0.86,
PyAV 14.2.0 and pytest 8.3.5. No physical Android phones were accessible.

## Source inventory

Created:

- `app/automation/api/__init__.py`, `context.py`, `device.py`, `errors.py`,
  `models.py`: public functions/types/errors and bound execution context.
- `app/automation/backends.py`: serial-bound Android and explicit fixture adapters.
- `app/projects/library.py`: shared contained image-library lookup.
- `app/editor/catalog.py`: assistance generated from actual callable signatures.
- `app/ui/execution_panel.py`: independent run/status/line/error presentation.
- `examples/visual_script.py`, `explicit_device_script.py`, `run_visual_fixture.py`.
- `tools/probe_script_editor.py`.
- `tests/test_automation_api.py`, `test_automation_api_waits.py`,
  `test_script_backends.py`, `test_image_library.py`, `test_script_runtime.py`,
  `test_script_service.py`, `test_script_editor.py`, `test_script_workbench.py`,
  `probe_script_workbench.py`, `test_script_project_ui.py`,
  `probe_script_project_ui.py`.
- `docs/SCRIPTING_API.md`, `docs/SCRIPTING_ENGINE.md`.

Modified:

- `app/automation/runtime.py`, `qt_service.py`: complete API binding, project
  imports, pause/resume, source reporting, main module and traceback fidelity.
- `app/devices/adb.py`: validated Android app/text actions, capture/timeout error
  classes and zero-exit Android failure detection.
- `app/editor/bridge.py`, `widget.py`, `editor_web/editor.js`, `style.css`:
  generated assistance, readonly image previews, warnings, state/line decorations.
- `app/ui/window.py`, `capture_dialog.py`: project context, shared/assigned runs,
  trust snapshots, controls, output/status, capture-to-click and error handling.
- `app/main.py`, `pyproject.toml`, `uv.lock`: current diagnostics/version 0.2.0.
- `tests/probe_ui_safety.py`, `probe_device_workbench.py`: fixture host hooks and
  explicit project context for preserved workflows.
- `README.md`, `docs/BLUEPRINT.md`, `PHASES.md`, `DEVELOPMENT.md`,
  `DEVICE_INTEGRATION.md`: current instructions and historical-stage links.

No Git commit/push, Windows installer, environment publication, OCR, recorder,
breakpoint debugger, scheduler or updater was introduced.

Updated startup instructions were saved successfully to the cloud environment
draft. Installation commands and dependency requirements remain unchanged.
Review/save the draft in environment settings and publish to retain the updated
snapshot; draft persistence does not establish publication or fresh-task restore.

## Remaining limits and hardware checks

- Physical screenshot-to-match-to-tap, application launching/stopping, text input,
  Wi-Fi/USB disconnect timing, two real-phone scripts and device/encoder behavior
  are unverified. Previous video protocol/decoder fixture results remain valid;
  this stage does not turn them into hardware evidence.
- Windows 10/11 x64 remains the target, but only Linux was exercised. Driver,
  WebEngine deployment, DPI, actual Windows spawn and clean-machine packaging
  acceptance are outstanding.
- Pause is a Python/API safe-point operation, not OS suspension of every thread
  or native call. Image timeouts are wall-clock budgets including pauses and may
  wait for bounded in-flight native operations to return. Stop can terminate an
  uncooperative worker; already-dispatched Android input cannot be reversed.
- `typeText` intentionally supports a conservative ASCII subset. Scroll and drag
  use supported swipe commands, not native scrollability detection or raw
  continuous multitouch. App-specific interpretation requires hardware tests.
- Templates are single-scale correlation targets. Similarity, search regions and
  offsets are implemented; OCR, multi-scale variants and richer recognition
  policy engines remain separate future work.
- Monaco provides this API's completion/signature/docs and syntax checks, not
  general project-wide Python semantic intelligence. Source highlighting is not
  a step debugger. Project choice/file assignments are session context, not
  persisted task schedules. `project.json` is a discovery marker, not a full
  project-settings parser in this increment.
- Arbitrary trusted Python runs with host-user permissions. Built-in contained
  image lookup, process isolation and leases do not restrict deliberate OS/ADB
  access or fully contain user-created descendants. The bridge never executes
  scripts or sends device commands.

For hardware validation, connect two authorized phones on a supported desktop,
choose a project and capture real `images/start.png`/`reward.png` targets. Run
the visual examples on one phone, then shared source and separate assigned files
on both. Verify exact target/offset/region coordinates, appearance/vanish timeouts,
supported text/app commands, pause/resume/stop, and typed failure on one phone
while the second continues. Disconnect/reconnect during recognition and paused
execution; confirm stale work never resumes automatically. Repeat on Windows
and record OS, drivers, Android versions, observed limits and actual results.
