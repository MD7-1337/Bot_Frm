# Technology decisions and risk register

Status: Phase 0 design baseline, 2026-10-29. Proposed integrations become accepted only after their gates pass. Version/command details in the repository manifest and executable tests take precedence over illustrative examples.

## ADR 001 — Qt Widgets and Python 3.12

**Decision:** retain the required Python/PySide6 architecture. Start with Python 3.12 and PySide6 6.8.3 for one consistent Qt/QtWebEngine dependency set. Use QMainWindow/QDockWidget; avoid a parallel QML or browser application shell.

**Reason:** Qt supplies native docking, input, accessibility and multiple-monitor support. Python's spawn model supports managed automation processes. The editor is the only initial WebEngine surface.

**Costs:** a large runtime, Chromium subprocess/resource deployment and Windows graphics-driver differences. Never fork after initializing Qt. A successful Linux headless launch does not establish Windows compatibility.

**Gate:** real editor bridge round-trip; clean Windows startup, DPI change, WebEngine child-process packaging, orderly shutdown and repeated launch tests. Audit supported Windows versions for every pinned Qt patch before release; do not promise unsupported OS builds.

## ADR 002 — Local Monaco with a narrow bridge

**Decision:** bundle Monaco 0.52.2 resources from an integrity-pinned npm archive; the setup helper requires no Node runtime. The editor web bridge exchanges validated text/document metadata and diagnostics. It does not execute scripts, select arbitrary files or issue device commands.

**Reason:** core editing must work offline. Node is not a desktop runtime requirement. Keeping host execution behind a host-owned trust/device dialog limits accidental bridge authority.

**Costs:** explicit local worker/resource URLs, asset integrity, Qt resource packaging and navigation/request restrictions need testing. Monaco is not a Python language server.

**Gate:** local assets loaded with external network unavailable; Unicode edits round-trip; stale revisions rejected; syntax errors marked without execution; attempts at unexpected navigation blocked. Phase 3 adds API intelligence and separately evaluates a project language service. Never label syntax-only diagnostics as full Python analysis.

## ADR 003 — scrcpy protocol experiment with explicit fallback

**Implementation update:** a video-only scrcpy 3.1 client with PyAV 14.2.0 is now
implemented and fixture-tested. Source URLs, wire assumptions, artifact digest,
resource ownership and hardware acceptance are recorded in STREAMING.md. This
does not close the real-device gate below. The native desktop scrcpy executable
is optional; the embedded client uses the exact Android server artifact.

**Decision:** investigate a matched scrcpy 3.1 client/server baseline and maintained H.264 decoder. Keep transport/decoding independent from widgets. Do not use native-window reparenting as the primary embedded architecture. Provide a labeled ADB screenshot fallback and managed external scrcpy fallback.

**Reason:** upstream scrcpy protocol is version-sensitive, while reparenting its SDL window is fragile across focus, DPI, lifecycle and distribution. Rendering decoded frames in Qt provides predictable overlays and coordinates.

**Costs:** binary framing, codec configuration, buffer ownership and control protocol work; PyAV/FFmpeg footprint and licensing. ADB screenshots have significant latency/CPU overhead and cannot satisfy a low-latency stream claim.

**Gate:** read the matching official protocol; test video/control against real phones, orientation/codec changes, repeated disconnect/reconnect and two-device isolation. Record versions, models, Android releases and actual FPS/latency. Until that passes, embedded scrcpy streaming is **unverified**. Command-construction fixtures do not prove hardware behavior.

## ADR 004 — Device ownership and spawned workers

**Decision:** one independent spawned run context per assigned serial, bounded by a configurable worker limit; one application-wide serial lease shared by manual, scheduled and scripted actions. Keep UI event handling asynchronous.

**Reason:** shared scripts need independent variables/progress and isolated failures. Explicit serials prevent ADB default-device cross-talk. Spawn is compatible with Windows.

**Costs:** startup and IPC overhead; arbitrary Python can hang, spawn children or access the host. Cooperative cancellation alone cannot stop all scripts. A hard-stop policy must revoke dispatch, confirm worker exit and clean resources.

**Gate:** two fixture serials execute concurrently without crossover; duplicate lease rejected; one worker failure does not stop the other; cancellation and forced termination bounded; no leaked managed workers after close. Repeat with two actual phones before hardware acceptance.

**Security limit:** workers are not sandboxes. Built-in API permission checks do not restrict arbitrary Python. App-local leases do not stop another ADB client. No claim of safe execution of untrusted code is permitted without a separately implemented OS isolation boundary.

## ADR 005 — OpenCV headless, defined score semantics

**Decision:** use NumPy 2.2.4 and opencv-python-headless 4.11.0.86 for initial image proofs. Match immutable original-device frames, not rendered previews/overlays. Define color order, clipping and score behavior in tests.

**Reason:** the headless wheel avoids conflicting Qt plugins; template matching is a focused initial engine. OCR, colors and UI hierarchy remain independent adapters.

**Costs:** templates vary with resolution/theme/animation; constant-color images can make normalized correlation misleading. Define the matching method and reject or handle degenerate templates explicitly. Use NMS/overlap filtering and return ambiguity rather than blindly select unsafe actions.

**Gate:** deterministic fixtures with known locations, threshold boundary, bad images, region offsets, negative results, multiple matches and constant-image cases. No score is described as a probability. Hardware screenshot validation is separate.

## ADR 006 — Offline OCR evaluation

**Decision:** evaluate Tesseract 5 via subprocess and TSV output before adding a heavyweight ML engine. OCR is not implemented merely because its command can be found.

**Evaluation:** compare accuracy on small game fonts, scaled crops, multilingual content and low-contrast screenshots; measure cold/warm latency and memory. Verify exact executable and traineddata compatibility. Preserve bounds and engine confidence when available. Allow engine/language absence with an actionable capability error.

**Gate:** recorded fixtures and language models, expected text/bounds, timeout/cancellation and malformed-output tests. Third-party model downloads must be integrity-verified and optional; the installed core must work offline.

## ADR 007 — File projects and SQLite metadata

**Decision:** keep ordinary UTF-8 Python/images in a versioned portable project directory; store machine-local device aliases, settings, schedules, trust approvals and run history in SQLite.

**Reason:** projects remain understandable outside the IDE while SQLite provides transactional due-run and history updates.

**Costs:** two persistence lifecycles require reconciliation. Project paths can move; source digests and file versions must invalidate stale trust. Atomic saves must preserve external changes. Export must resist traversal/symlinks/decompression bombs.

**Gate:** migration rollback/recovery, imports with hostile paths, round-trip reopen/export, unsaved-buffer recovery, interrupted-run handling and transactional trigger deduplication. Secrets and trust approvals are excluded from project exports.

## ADR 008 — Debugging and bounded recovery

**Decision:** use debugpy/DAP per worker; implement recovery as explicit policies and checkpoints, not generic retry around every action.

**Reason:** Python debugging is a specialized protocol, and Android action completion can be ambiguous on timeout/disconnect. Repeating a tap may be unsafe.

**Costs:** debugger endpoints allow code execution. Bind to loopback, create only on request and keep them private. Pause/step semantics must coexist with cancellation and leases. A running Android command cannot be undone.

**Gate:** breakpoint/step/variables and exception inspection in one run while a second continues; emergency stop works while debugger is paused; reconnect does not silently replay a potentially completed operation. Policies carry attempt limits/backoff and a verified checkpoint state.

## ADR 009 — Windows packaging and optional updates

**Decision:** evaluate a Windows-built PyInstaller directory bundle for portable distribution and Inno Setup for installer distribution. Bundle approved runtime resources for offline use. User-controlled updates require authenticated metadata and verified artifacts.

**Reason:** directory bundles simplify QtWebEngine resource inspection, diagnosis and rollback compared with early one-file extraction. The installer wraps the tested portable payload and adds OS integration/uninstall.

**Costs:** exact WebEngine resources/locales, codecs, DLL dependencies and child-process paths need a clean-machine test. ADB, scrcpy, OCR and Qt components each have redistribution obligations. Antivirus signing/reputation and elevation behavior need release planning.

**Gate:** install/launch/uninstall on clean supported Windows x64 without Python/Node; offline editor/capture/automation; preserve projects/settings on upgrade; portable ZIP launch; corrupt update rejected; interrupted update recovers. No Windows artifact is claimed until actually built and tested on Windows. Signing credentials cannot be invented or committed.

## Preliminary third-party license inventory

This is an engineering inventory, not completed legal clearance. Generate a bill of materials for the exact release artifacts and include their notices/licenses. Check transitive components, model data and binary build options, not only the top-level Python package.

| Component | Initial license considerations / required release action |
| --- | --- |
| Python | PSF license; include notices for bundled runtime |
| PySide6 / Qt | LGPLv3/GPL/commercial options; choose a compliant distribution path, include notices and required relinking/source information; inspect each Qt module |
| Qt WebEngine / Chromium | Qt licensing plus extensive Chromium third-party notices; ship required resources/notices |
| Monaco | MIT; retain copyright/license in local asset bundle |
| NumPy | BSD-style license and bundled binary dependency notices |
| OpenCV | Apache-2.0 for current OpenCV; inspect wheel notices and bundled libraries |
| ADB / platform tools | AOSP components commonly Apache-2.0; inspect exact binary distribution and SDK/download redistribution terms rather than assume every archive may be bundled |
| scrcpy | Apache-2.0; inspect distributed SDL/FFmpeg/dependency notices and codec build options |
| PyAV / FFmpeg | PyAV license and actual linked FFmpeg LGPL/GPL configuration must be audited before bundling |
| Tesseract and traineddata | Apache-2.0 upstream; verify chosen executable build and each model/archive license |
| debugpy | MIT and dependency notices for the exact packaged version |
| PyInstaller | GPL with bootloader exception; follow exact version's redistribution terms |
| Inno Setup | Review current official licensing/commercial-use terms for the selected version |
| Icons/fonts | Use original, OS-provided or explicitly redistributable assets; include their licenses |

## Risk register

| Risk | Severity | Mitigation / exit evidence |
| --- | --- | --- |
| scrcpy protocol/decoder mismatch | High | Matched version pin; protocol fixtures plus real-device negotiation/reconfiguration tests; fall back visibly |
| Wrong device or concurrent manual/script input | High | Verified serial on every target operation, generation-checked lease, concurrency tests, explicit takeover |
| Untrusted Python damages host | High | Clear trusted-code approval, digest tracking, no sandbox claim; investigate true OS isolation separately |
| Stale frame leads to unsafe action | High | Frame IDs/freshness deadlines, revalidation before sensitive actions, stop on ambiguous disconnect |
| Worker or queue hang freezes GUI | High | No blocking GUI joins, bounded channels, status path independent of logs, cancellation/termination tests |
| QtWebEngine fails in packaged Windows | High | Clean-Windows subprocess/resource/DPI/GPU/offline smoke matrix before release |
| Recovery repeats irreversible action | High | Default stop, bounded policy only for known-idempotent steps, checkpoints and user-visible evidence |
| Project import escapes root or leaks secrets | High | Canonical containment, archive limits, no symlink traversal, export allowlist, negative tests |
| Preview and recognition exceed host resources | Medium–high | Shared latest frames, bounded worker count, background FPS, region matching and actual benchmarks |
| Windows signing/release access unavailable | External prerequisite | Finish source/tests/docs; acquire signing/release credentials securely only when packaging stage needs them |
| Required Android capability absent | Medium | Probe and report unavailable/unauthorized states; no fabricated metadata; documented fallback |
| Dependency/version aging | Medium | Review vulnerabilities/support, controlled upgrades with offline/bridge/hardware regression matrix |
