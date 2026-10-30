# Delivery phases, gates and test strategy

The subsequent foundational Python engine now implements the requested image,
touch, timing and Android API with worker pause/resume and editor integration;
see [SCRIPTING_ENGINE.md](SCRIPTING_ENGINE.md). Hardware acceptance for the
preview and image-to-tap gates remains open. This does not close unrelated
OCR, recorder, debugger, scheduler or Windows release phases.

Current increment: the device/video/capture foundation now implements portions
of phases 1–3, with results in [DEVICE_INTEGRATION.md](DEVICE_INTEGRATION.md).
The real-phone and Windows acceptance gates below remain open. No unrelated
advanced phase was started.

The requested first increment is the blueprint and Phase 0. This plan preserves the full product scope without representing future work as delivered. Each phase integrates and tests the previous work before adding the next layer. Phase 0's fixture proofs do not satisfy later physical-device or Windows release gates.

## Milestones

| Phase | Scope and dependencies | Required acceptance evidence | Follow-on work |
| --- | --- | --- | --- |
| 0 — architecture and technical proofs | Blueprint, dependency pins; actual PySide6/WebEngine/Monaco bridge; serial-scoped ADB adapter; screenshot/coordinate and external scrcpy fallback proofs; independent spawned workers; recognition fixtures; packaging/license evaluation | Current-run unit/integration results; actual Qt local editor round-trip; documented fallback for unverified streaming; precisely labeled missing hardware/Windows checks | Stabilize foundation and execute hardware experiment |
| 1 — application foundation | Depends on phase 0 integration decisions; shell/navigation/docks, themes/settings, USB/Wi-Fi connection/authorization and device metadata | Repeated startup/shutdown; real USB device discovery, unauthorized/offline handling; persisted validated settings; GUI remains responsive during bounded discovery | Reliable streaming/control |
| 2 — phone preview/control | Matched scrcpy server/client decision; decoder; shared frame store; grid/detach/fullscreen/zoom/rotation; pointer/keyboard/navigation; capture | Real phone visible and controllable inside Qt; two devices routed correctly; crop/letterbox/rotation boundaries; disconnect and cleanup; measured latency/resource use | Capture-to-code and assets |
| 3 — Script Studio | Local Monaco and project lifecycle; tabs, atomic source save, image capture/crop/assets, insertion toolbar, reference thumbnails, syntax/API assistance; separately evaluated language intelligence | Real capture → crop → save asset → insert valid Python → reopen project; missing asset and file conflict handled; offline editor works; ordinary source unchanged by decorations | Bind full automation API |
| 4 — automation runtime | Device broker/leases, trusted execution, API bound context, matching/waits, failure context and cancellation | Real script detects and taps known target; no default-device actions; zero/finite timeout tests; cancellation during capture/recognition; explicit arbitrary-Python security limitation | Shared/independent phone execution |
| 5 — multi-device execution | Resource cap, independent workers, shared and different sources, group controls/status, independent failure | Two actual phones progress independently with no command crossover; one failure leaves other active; takeover and emergency stop revoke dispatch; record CPU/RSS/queues | Advanced recognition/recorder |
| 6 — recognition and recorder | OCR evaluation and models, colors, optional UI hierarchy, variants/scales/preprocessing/NMS; match tester; record controlled input/timeline/code replay | Known-text/image/color fixtures; actual phone match overlays/coordinates; record → edit generated Python → replay; unsupported UI/OCR reports honest error | Debugging and bounded recovery |
| 7 — debugger and recovery | Per-run debugpy/DAP, source mapping, stack/variables, recognition inspection, evidence, retry/backoff/checkpoints | Breakpoints and stepping on one phone while another runs; stop while paused; expected failure captures diagnostics; reconnect refuses blind unsafe replay | Scheduling and workflows |
| 8 — tasks and games | SQLite migrations; queues/priorities/dependencies; trigger dedupe, missed-run policy, per-device arbitration, package switching | Real scheduled sequential workflow across apps; restart does not duplicate run; cyclic dependencies rejected; retries/duration bounded; task history accurate | Project/UX completion |
| 9 — projects and advanced UX | Layout presets/themes/fonts/shortcuts, backup/version history, autosave/search/import/export/migration, optional Git, tutorials and accessibility | Restart restores usable layout on changed displays; project export/reopen preserves sources/assets without credentials; conflict and recovery tests; keyboard workflows | Release hardening |
| 10 — optimization/release | Benchmarks/stress, security review, diagnostics, exact dependency/license inventory, Windows bundle/installer, verified optional updates | Clean Windows without Python/Node; offline launch/edit/control/run; installer/uninstall and portable tests; upgrade preserves projects; corrupt update rejected; measured hardware limits | Signed release and ongoing maintenance |

Milestones are dependency gates, not dates. Schedule estimates require the hardware experiment and actual integration evidence; do not promise a production release from the current Linux session.

## Phase 0 proof checklist

Track these separately in the current validation report:

| Proof | Evidence to collect | What it does not establish |
| --- | --- | --- |
| Qt/WebEngine import and actual window/page | Real runtime launch and orderly teardown | Clean Windows bundle compatibility |
| Offline Monaco + QWebChannel | Editor loaded local resources; Unicode source and diagnostics round-trip; insertion produces ordinary Python | Project-wide Python language intelligence, debugger or complete editor UX |
| ADB command/parse/error handling | Exact argv includes `-s` for target calls; unauthorized/offline parsing; timeouts; actual version/discovery if installed | Access to physical devices when none are attached |
| Embedded screenshot fallback | Valid PNG decode/render; latest-only capture; correct coordinate inverse | Low-latency embedded scrcpy streaming |
| External scrcpy management | Explicit serial, supported argv and owned-process cleanup; real launch if executable/device available | A stable embedded scrcpy widget or verified video/control protocol |
| Coordinate transform | All four rotations, letterboxes, bounds, round-trip pixel centers | Every DPI/zoom/rotation path on Windows monitors |
| Worker isolation | Two fixture serials, independent globals/actions, one failure independent, duplicate lease rejected | Two physical phones or hostile-code sandboxing |
| Cancellation | Cooperative wait cancellation, force-stop of busy loop, cleanup/restart | Undo of already dispatched Android command or arbitrary child process containment |
| Recognition | Known deterministic images, thresholds, offsets, no-match/bad-input and overlap cases | Recognition robustness on arbitrary real games |
| Packaging evaluation | Dependency/resource/license inventory and Windows release test plan | A built or tested Windows executable/installer |

A documented fallback satisfies the Phase 0 architectural decision requirement where the primary transport cannot be demonstrated here. It does not close the later hardware acceptance gate. Keep failed, passed, skipped, unavailable and unrun outcomes separate. A test collecting zero cases is not validation.

## Test layers

### Unit tests

- Transform math: fit rectangles, letterbox rejection, rotations, nonsquare sources and pixel boundaries.
- Device validation/selection: unknown, unauthorized and offline states; special serial strings; command construction without shell expansion; duration and numeric limits.
- Recognition: original frame coordinates, threshold inclusivity, multiple/overlapping results, constant images, bad image sizes and missing files.
- API contracts: argument types, finite limits, correct return/error classes, no context, unsupported features and cancellation.
- Settings/project schemas: malformed versions/types, nonfinite JSON values, path traversal/symlink containment, atomic-save conflicts and migration recovery.
- Tasks: legal state transitions, dependency cycles, retry/backoff limits, missed runs and trigger uniqueness.

### Integration tests

- Actual Qt WebEngine loads local Monaco and exchanges source/diagnostics through WebChannel. Include text that would execute if improperly evaluated and confirm it remains inert.
- Spawn workers rather than substitute threads: validate isolated state, bounded event handling, duplicate leases, abrupt exits and force-stop cleanup.
- Inject fake ADB subprocess results for deterministic errors; use actual ADB version/discovery as a separate environment probe.
- Decode capture/video fixtures and test bounded frame ownership, freshness and orientation updates.
- Exercise scheduler/coordinator/SQLite transactions across simulated restart; verify result files/logs belong to the current run.
- Exercise per-worker DAP and private endpoint cleanup when debugging is implemented.

### Hardware and Windows acceptance matrix

Record machine model/CPU/RAM/GPU, Windows build, DPI/layout, Python/Qt/ADB/scrcpy/decoder versions, phone model and Android version, USB/Wi-Fi mode and observed authorization state. Avoid storing serials in publicly shared diagnostics without consent.

1. Connect/authorize USB phone 1, then phone 2. Verify actual serial identity and separate previews.
2. Capture/crop an asset on phone 1 and insert valid image-based Python.
3. Run on phone 1, then the same source independently on phone 2; run distinct sources concurrently.
4. Force a no-match and verify bounded recovery. Disconnect one phone during execution and ensure the other remains active.
5. Rotate/change resolution, detach/reattach/fullscreen and move windows between monitors at different scaling. Tap visible landmarks; reject letterboxes.
6. Set breakpoints/inspect variables in one run while the other continues. Emergency stop while paused and during input.
7. Record controlled gestures, edit the resulting Python and replay. Do not claim physical touches outside the application are recorded.
8. Schedule a sequence across two packages on one phone. Restart before/after due time; verify selected missed-run policy and no duplicate unsafe action.
9. Export/restore project; test unsaved buffers, backup recovery and missing assets; restart and restore layout.
10. Install clean Windows bundle without Python/Node; run offline. Test portable release, uninstall, upgrade/project preservation, invalid update and recovery.

Mock tests supplement this matrix and must not be reported as completing it.

## Performance evaluation

Measure idle, one-phone, several-phone and progressively larger workloads. Include active video, background previews, region/full-frame recognition, long runs, reconnects and repeated project open/close. Record actual FPS, dropped/stale frames, capture-to-render latency distribution, recognition duration, CPU/RSS for host/workers, queue depth and error counts. State hardware and test duration with every result. Do not extrapolate a short fixture run into a sustained 20-device promise.

Start conservative: a configurable low worker cap, at most one in-flight capture per device and latest-frame queues of depth one. Increase concurrency only after measuring. Low-resource/balanced/responsive profiles adjust actual tested settings; unavailable metrics remain blank rather than invented.

## Phase reporting template

For each completed increment, publish a concise report with:

1. Implemented features and exact source modules.
2. Commands and working directories required to run and test them.
3. Test counts/outcomes from the actual run, including skips and failures with diagnosis.
4. Hardware/platform matrix exercised and evidence artifacts.
5. Remaining limitations and release blockers.
6. Next phase tasks and the gate they will resolve.

Do not call the application production-ready while any release gate is unrun or blocked. Missing hardware or signing access is an external prerequisite, not a reason to fake successful tests or silently replace the agreed technology.

## Documentation delivery map

- Phase 0: BLUEPRINT.md, DECISIONS.md, PHASES.md, developer run/test instructions and current validation report.
- Phases 1–3: installation/dependency setup, first run, USB/Wi-Fi connection troubleshooting, Script Studio manual, image capture tutorial and source/asset conventions.
- Phases 4–6: tested API reference/examples, multi-device tutorial, recognition/match testing guide and recorder tutorial.
- Phases 7–8: debugging/recovery tutorial and task scheduling/missed-run guide.
- Phases 9–10: backup/import/export/migration guide, accessibility/layout customization, contribution guide, release/packaging/update instructions, third-party notices and known limitations.

Documentation for future features is a delivery obligation. Avoid publishing tutorials that imply an unimplemented UI or API exists.
