# Phase 0 validation report

Historical baseline: the next device/video/capture increment is reported in
[DEVICE_INTEGRATION.md](DEVICE_INTEGRATION.md). Statements below describe Phase 0,
including features that were subsequently implemented.

Date: 2026-10-29. Scope: engineering blueprint and technical integration proofs. **This is not acceptance of the finished product or a Windows release.**

## Environment exercised

- Linux x86-64, kernel `6.18.55`, glibc 2.41; headless cloud machine.
- Python 3.12.14, uv 0.12.23, PySide6/Qt 6.8.3, Monaco 0.52.2.
- NumPy 2.2.4, opencv-python-headless 4.11.0.86, pytest 8.3.5.
- Google platform-tools 37.0.1, ADB `1.0.41`, build `37.0.1-15733141`.
- No attached Android devices; no scrcpy executable; no Windows host tested.

## Outcomes actually obtained

| Check | Result and evidence |
| --- | --- |
| Complete final suite with GUI tests enabled | **119 passed, 0 failed, 0 skipped**, pytest exit 0, 8.34 seconds. Runtime is a short fixture test measurement, not a phone-scaling benchmark. |
| Real Monaco / QWebChannel | Real Chromium page loaded local Monaco. Probe reported `ready`, Unicode source `roundtrip`, syntax markers and cursor `insertion` all true. |
| Integrated window | Actual workbench startup/cleanup passed; local Monaco ready and three real Qt docks present. |
| UI safety regression | Real Qt widget PNG decoding and pointer events, exact pending-run lease confirmation, emergency input invalidation, GUI-thread callbacks, and deferred shutdown passed. This test substitutes only its editor widget; the separate WebEngine tests exercise the real editor. |
| ADB routing/errors | Subprocess fixtures verify explicit serial argv, offline/unauthorized parsing, missing executable, malformed PNG, timeouts and validated controls. |
| Actual ADB executable | `AdbClient.version()` succeeded. `AdbClient.devices()` succeeded with `[]`. Tool installation/discovery works; no physical connection is established. |
| Preview transforms | Letterboxes, bounds, all four rotations and fractional-scale pixel-center round trips passed. Synthetic PNGs are explicit fixtures. |
| Spawn worker isolation | Actual independent Python processes with explicit mock serials; no action crossover, independent failure, leases, trust validation, bounded JSON events, cancellation and cleanup passed. |
| Async Qt runtime service | Two spawned runs, owner-thread routing, bounded submission, GUI timer responsiveness during cancellation, emergency latch/reset and bounded shutdown passed. |
| Recognition | Actual OpenCV on deterministic synthetic RGB frames: known matches, multiple results, region offsets, NMS, bad/constant templates, finite threshold validation, no-match and immutable input behavior passed. |
| Editor security boundaries | Syntax analysis did not execute source. Request-filter fixtures reject remote HTTP(S), arbitrary local files and unexpected qrc paths. |
| Reusable setup | `bash tools/setup.sh` completed after initial provisioning; locked dependencies reused, Monaco and ADB redownloaded and integrity-checked successfully, diagnostics returned expected paths/versions. |
| Design schemas | Every JSON example parsed with `json.loads`; proposed SQLite DDL executed successfully against an in-memory SQLite database. This does not implement project/schedule persistence. |
| Source syntax | `python -m compileall -q app tools examples tests` completed successfully. |

The default test command intentionally skips three GUI integrations unless `STUDIO_GUI_TESTS=1`. The final result above enabled and ran all three. No hardware tests were substituted with an unexplained skip or counted as passing.

## Reproduce the final suite

From `/workspace/Bot_Frm`:

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu' \
XDG_CONFIG_HOME=/tmp/aas-tests .venv/bin/python -m pytest -q
```

This managed cloud instance requires supported escalated execution for Chromium/multiprocessing local IPC. A first attempt inside the command sandbox failed with an OS `Operation not permitted` at Chromium startup; the corrected external-sandbox execution passed. The browser sandbox override is only for isolated headless tests and is not part of normal application launch. Headless GPU/Vulkan warnings did not prevent the actual editor behavioral assertions from passing.

System APT installation was unavailable due filesystem permissions. Development ADB was instead obtained from Google's official HTTPS SDK repository, retaining its published archive checksum verification. No package/TLS/checksum verification was disabled. Monaco's full archive passed its pinned SHA-512 integrity digest. No secrets were needed or added.

## Configuration saved

The cloud configuration draft save succeeded for **`install_script`** and **`start_skill`**. They capture the tested working directory, locked setup commands, integrity-checked asset/tool downloads, startup/diagnostic instructions, headless checks and limitations. No network domains, secret requirements or repository membership were changed.

Saving a draft does not publish it or validate restoration in a new task. Review and save the configuration in environment settings, then publish the environment to retain the prepared snapshot. No publication or fresh-task restoration was performed here. Source files remain local; no Git commit or push was made.

## Unrun / unavailable acceptance gates

| Gate | Status / next action |
| --- | --- |
| Real phone PNG, tap/swipe, authorization and disconnect | Unrun: attach an authorized Android phone with working USB/Wi-Fi transport. |
| Two-phone isolation on hardware | Unrun: attach two phones; repeat context, control and independent-failure scenarios. Mock worker tests do not close this gate. |
| External scrcpy launch/playback | Unrun: executable and phones absent. Adapter command/lifecycle fixtures passed. |
| Embedded scrcpy video/control | **Not implemented.** Prove matched client/server protocol and decoder, orientation/reconfiguration, cleanup and latency on hardware. Screenshot fallback remains visibly labeled. |
| Full editor/API, OCR, recorder, DAP, scheduler and project persistence | Planned later phases; no production completion claim. |
| Clean Windows launch, DPI/monitor matrix | Unrun: requires supported Windows x64 machines. |
| Windows installer / portable executable | **Not built or delivered.** Packaging evaluation and release tests are documented only. |
| Long-running performance / 20-device scaling | Unrun. No FPS, capacity or resource benchmark is claimed. |
| New-task snapshot restoration | Unrun; draft is saved, publication remains a user action. |

The implemented subset uses host-trusted Python, coordinator-local leases and direct validated ADB adapters. It does not implement an OS sandbox, host-wide command exclusion, descendant-process containment, full production broker, safe arbitrary-code execution, or an authenticated updater. The blueprint specifies those boundaries and future gates explicitly.

## Next implementation tasks

1. Validate the current capture/input/worker subset with actual Android hardware and a Windows development host.
2. Run the pinned scrcpy/decoder experiment; keep fallback behavior until the primary embedded stream passes its hardware gate.
3. Advance Phase 1 device metadata, connection/pairing/settings and workspace foundations, preserving the tested adapter/runtime boundaries.
4. Continue the remaining phases in `PHASES.md`; stabilize the complete scripting API before advanced recorder/debugger/scheduling work.
