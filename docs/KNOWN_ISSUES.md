# Current limitations and acceptance gates

Source version remains **0.2.0 Alpha**. This increment is substantial development,
not a feature-complete Alpha candidate or Beta release.

- Real USB/Wi-Fi phones, scrcpy frames, rotation, touch mapping, reconnect and
  two-phone independence are **NOT VERIFIED** in this Linux cloud environment.
- Native Windows EXE/ZIP/installer and Ubuntu portable builds have passed frozen
  workflow smoke tests. Source acceptance is recorded per commit in
  [current validation](RELEASE_VALIDATION.md). Binary downloads remain blocked by
  licensing clearance; Windows 10/11 interactive desktop and hardware acceptance
  remain unverified.
- Debugger snapshots support bounded project Python imports and per-file
  breakpoints. Native extensions, already-loaded/outside-project modules and user
  import hooks retain normal Python behavior. Conditional/function breakpoints,
  watch expressions and evaluation are deferred.
- Debugger pause can wait for native code. Stop still uses bounded owned-process
  termination. Arbitrary trusted script descendants are not an OS sandbox.
- Task queues arbitrate this application instance. Named groups expand into
  explicit devices; ordered workflows correlate steps to each workflow run.
  Arbitrary branching graphs, holiday calendars and distributed/multiple-instance
  arbitration are deferred.
- Task approval lasts for this application session. Reconnect/reset, restart,
  source changes and emergency stop require approval again. Imported task
  definitions are disabled/unapproved. Ordinary scheduled runs still read imported
  Python/helpers/assets from disk; review the whole project. Debug mode captures
  bounded approved Python imports separately.
- A scheduler cannot guarantee exactly-once Android actions. Lost acknowledgments
  and interrupted dispatch remain uncertain; unsafe input is never blindly
  retried. Read-only recovery checkpoints are in-memory, not persistent resumes.
- Project backup/export covers saved files. Dirty editor buffers need explicit
  saving; configurable recovery copies preserve unsaved buffers separately.
  Recognition/run presets are editable and deletion moves projects to reversible
  trash; permanent deletion is left to the user. Archives are bounded and
  intentionally exclude hidden files, logs and common credential files; review
  scripts for embedded secrets before sharing.
- Optional OCR requires a locally configured Tesseract engine/languages; stylized
  game text and arbitrary image variations cannot be guaranteed.
- Short simulator benchmarks establish only the measured fixture workload.
  Sustained streaming load, long-run leak testing and real-device limits remain
  acceptance work.
- Redistribution needs repository license confirmation, Qt/WebEngine/Chromium
  notices, FFmpeg/PyAV license review and Android-tool terms review. Actual payload inventories and source-built LGPL FFmpeg/PyAV improve evidence;
  unsigned builds alone do not resolve these obligations.

See [the development report](ALPHA_COMPLETION.md) for evidence and next steps.
