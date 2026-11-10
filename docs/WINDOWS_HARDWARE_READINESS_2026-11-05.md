# Windows hardware readiness checkpoint

This work continues on `recovery/continue-alpha-2026-11-01`. Physical Android
hardware was unavailable here. A phone visible to standalone scrcpy but absent
from Studio remains an **unconfirmed field issue** until both executables and
their device listings are compared on that Windows computer.

## Audit and smallest safe sequence

The existing application already has serial-bound ADB operations, a device
registry, background polling, a connection wizard, eight-stage diagnostics,
Monaco readiness and breakpoint handling, approved source snapshots, independent
worker processes, a one-folder PyInstaller package, an extracted EXE smoke, and
an intentional redistribution gate. The current branch already resolves
`platform-tools/adb.exe` beside the frozen executable and shows discovery errors.
These systems were retained.

The initial source run in this workspace was **945 passed, 6 failed,
33 skipped** without GUI opt-in. It overlapped the first discovery patch, so it
is an environment baseline rather than an untouched-commit result. All six
failures were scrcpy socket tests;
five directly reported `PermissionError: [Errno 1] Operation not permitted` in
the restricted workspace. The initial opt-in GUI run was **950 passed, 27 failed,
3 skipped**; it likewise overlapped the first patch, and many failures reported
Qt WebEngine sandbox denial. Native tests
outside that restriction are the acceptance gate. Historical Windows package
results in earlier documentation apply to older commits only.

After the fixes, the complete native Ubuntu source and GUI run passed:
**985 passed, 0 failed, 3 optional OCR skips**. The focused discovery,
comparison, report, and packaging tests passed **62 of 62**. The Windows CI
result and this commit's extracted EXE smoke must be read from the new workflow
run after pushing; older workflow artifacts do not validate this change.
The source equivalent of the release smoke passed with all ten GUI checks,
including report generation, debugger, worker, project restore, and cleanup;
its `frozen` field was correctly `false`.

1. ADB parser: reject malformed `adb devices -l` rows as discovery failures.
   Previously these rows could be skipped, producing an apparent empty list.
2. Discovery ownership: ignore a pending result from an ADB client that was
   replaced in Settings and immediately refresh with the new client.
3. Reporting: maintain a bounded local event log, expose its path, provide a
   reviewable bug report, and compare Studio's ADB with an external executable.
4. First run and packaging: show the existing dismissible wizard once, retain
   explicit invalid ADB choices as visible failures, and exercise report
   generation in the frozen smoke.

No script or debugger engine was replaced. Existing editor, worker, and debugger
tests remain the regression evidence for those components. The report and event
log contain no screenshot pixels or script source by default. The comparison
may cause ADB itself to update its shared server when client versions differ;
it does not issue `kill-server` or alter Android authorization.

## Windows acceptance still required

Build the current branch on Windows and inspect the new `windows-frozen-smoke.json`
and build manifest. Then use Settings to note the effective ADB executable,
run Diagnostics with the phone attached, and use **Compare with external adb.exe…**
to select standalone scrcpy's ADB binary. Record each binary's version and
redacted discovery state. Follow [hardware acceptance](HARDWARE_ACCEPTANCE.md)
for screenshot, real video, input, scripting, debugger, disconnect/reconnect,
and shutdown. A source or simulated test does not verify those hardware steps.
