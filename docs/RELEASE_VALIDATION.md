# Cross-platform Alpha validation — 2026-10-31

Source version: **0.2.0 Alpha development**. Branch:
`feat/cross-platform-alpha-release`, based on `b6a7152` from
`feat/alpha-completion`. Main and previous development branches are preserved.

The pristine baseline passed **863 tests, 0 failures, 0 skips** in 107.36 seconds,
including the 23 existing Qt/WebEngine journeys. The final source commit is
`a1720b5d8a3b7c39e9b49e5555c840c3a6a5222c`: **926 passed, 0 failed, 0 skipped**
in 142.26 seconds, including **30 real GUI cases**. Exact case/module counts are
in [source evidence](validation/cross-platform-source-tests.json).

Implemented in this increment: bounded atomic autosave recovery copies and native
crash recovery; recognition and run presets; reversible typed-confirmation project
trash; device groups and occurrence-correlated ordered workflows; source snapshots
for imported Python debugging; persistent per-file breakpoints; a beginner connection
wizard and redacted report export; Windows/Ubuntu portable builders, installer
checks and actual frozen workflow acceptance. Native source callbacks now carry
tab identity and revision, preserving pending edits across rapid tab switches.

The frozen smoke exercises actual bundled Monaco, a stateful simulated phone,
OpenCV image click, debugger breakpoint/variables/step, recorder-generated Python,
scheduled worker, durable history and project archive restore. It approves only
built-in fixture code and never connects a physical phone. It runs after extraction
and relocation into a path with spaces, outside the source checkout.

Ubuntu targets glibc 2.35 using an Ubuntu 22.04 builder and a clean runtime image
with no system Python. Windows requires a native Windows runner. Both application
launchers retain normal WebEngine security defaults; sandbox overrides are confined
to explicit isolated headless test invocations. ADB, scrcpy server and Tesseract
remain user-selected external tools; no silent downloads or administrator changes.

## Actual Ubuntu deliverable

`dist/AndroidAutomationStudio-ubuntu-x86_64.tar.gz` — **320,654,228 bytes**
(approximately 306 MiB), with matching `.tar.gz.sha256` sidecar.

```text
e6cf489161b1edb8b2f35f36197852e83ab80e1bb6e3d3f4341db040d2f733c4
```

The archive contains `AndroidAutomationStudio/run-studio.sh` and the native
`AndroidAutomationStudio` executable plus its bundled runtime/resources. Its
BUILD_INFO identifies commit `a1720b5`, Python 3.12.15, PyInstaller 6.12.0 and
Ubuntu 22.04.5/glibc 2.35. Its application source/resource digest was independently
matched against the committed workspace, and the delivered checksum was verified.
The archive is a local workspace deliverable; no GitHub artifact upload occurred.

| Validation | Actual result |
| --- | --- |
| Linux source suite | 926 passed / 0 failed / 0 skipped; 30 GUI cases |
| Frozen builder extraction/relocation with spaces | PASS — real executable/Monaco, simulation, debugger, recorder, scheduled worker, persisted history and project restore |
| Clean Ubuntu 22.04 image without Python/python3 | PASS — same extracted package and workflow |
| Unprivileged Docker user `65534:65534` | PASS — packaged workflow, with headless-only browser test flags |
| Windows source/package/installer tests for this branch | 0 executed — publication blocked before CI trigger |
| Physical one-phone / two-phone tests | 0 / 0 executed — NOT VERIFIED |

Evidence: [package manifest](validation/cross-platform-package.json),
[builder frozen smoke](validation/cross-platform-linux-frozen-smoke.json),
[clean Ubuntu smoke](validation/cross-platform-ubuntu22-clean-runtime-smoke.json),
[no-Python runtime information](validation/cross-platform-ubuntu22-runtime-info.txt),
and [unprivileged smoke](validation/cross-platform-ubuntu22-nonroot-smoke.json).

The clean-runtime run measured 1,639.6 ms from workbench creation to ready Monaco,
252,522,496 bytes idle parent RSS and 272,154,624 bytes active parent RSS; maximum
recorded GUI heartbeat gap was 181.5 ms over this short 4.256-second workflow.
These are parent-only short probes, not total browser/worker memory or long-run
leak claims. Actual one/two/four worker fixture timings were 0.5115/0.6549/1.3238
seconds; see [measurements](validation/cross-platform-workers.json). Real preview
FPS, Windows performance and sustained loads remain unmeasured.

Failed preliminary package probes identified missing Qt native dependencies,
including `libatomic.so.1`; these were fixed before the successful tests above.
The editor tab/source callback race and a stream-test readiness race were fixed
before the final green suite. No stable release is published automatically.

## GitHub and Windows blocker

Automatic approval review rejected the push to `feat/cross-platform-alpha-release`,
because the preceding explicit chat authorization covered only `feat/alpha-completion`.
It did not accept the uploaded request as approval for the new branch. The blocked
push process was not executed. No alternate branch/transport was used, no remote
branch or PR was created, and no new Windows/Ubuntu CI run was triggered.
Explicit authorization of the new branch was requested in the chat and remains
necessary before publishing. GitHub API access also remains restricted; the
previous PR attempt returned `Forbidden` from `api.github.com`.

There is **no Windows ZIP or installer artifact** from this execution. The new
native Windows CI builder, extracted-app smoke, installer compiler and
install/uninstall tests are implemented but unexecuted. The observed earlier
[Alpha CI run](https://github.com/MD7-1337/Bot_Frm/actions/runs/41192436262) passed
Ubuntu source tests, failed Windows source tests and skipped Windows packaging;
that is historical evidence for `b6a7152`, not a pass for this branch.

After approval, push only this feature branch, inspect the actual cross-platform
run, repair any native Windows failures, retrieve its ZIP/installer/checksums,
then create an unmerged draft PR targeting `feat/alpha-completion` when API access
permits. The prepared description is [here](PULL_REQUEST_CROSS_PLATFORM_ALPHA.md).
Main and prior development branches were not modified; the environment
configuration was not published.

## Remaining acceptance

Release classification remains **Alpha development**. Windows binary evidence,
normal Windows desktop/DPI/multiple-monitor checks, physical USB/Wi-Fi/scrcpy,
one/two-phone routing/disconnect/emergency tests, sustained memory/CPU/preview
measurements and redistribution/notices/signing review still gate a cross-platform
Alpha candidate and Beta. The connection wizard/export and the full PASS/FAIL/
NOT VERIFIED procedure are in [REAL_ANDROID_TESTING.md](REAL_ANDROID_TESTING.md).
The school computer is not a development or build prerequisite.

The cross-platform workflow is
<https://github.com/MD7-1337/Bot_Frm/actions/workflows/cross-platform-alpha.yml>.
GitHub API access is restricted in this environment; normal public Actions pages
can be observed. Artifacts may require the user's GitHub login to download.
See [Windows](INSTALL_WINDOWS.md), [Ubuntu](INSTALL_UBUNTU.md),
[real Android testing](REAL_ANDROID_TESTING.md) and [remaining issues](KNOWN_ISSUES.md).
