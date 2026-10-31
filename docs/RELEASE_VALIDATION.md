# Cross-platform Alpha validation — 2026-10-31

Source version: **0.2.0 Alpha development**. Branch:
`feat/cross-platform-alpha-release`, based on `b6a7152` from
`feat/alpha-completion`. Main and previous development branches are preserved.

The pristine baseline passed **863 tests, 0 failures, 0 skips** in 107.36 seconds,
including the 23 existing Qt/WebEngine journeys. Final source and packaged evidence
will be recorded here after builds complete; a recipe is not a binary release.

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

Current artifact/build status is under active validation. Failed preliminary
Linux package probes identified missing Qt native dependencies, including
`libatomic.so.1`; those failures are not counted as successful packages.
Windows and real Android acceptance are **NOT VERIFIED** until actual evidence
is recorded. No stable release is published automatically.

The cross-platform workflow is
<https://github.com/MD7-1337/Bot_Frm/actions/workflows/cross-platform-alpha.yml>.
GitHub API access is restricted in this environment; normal public Actions pages
can be observed. Artifacts may require the user's GitHub login to download.
See [Windows](INSTALL_WINDOWS.md), [Ubuntu](INSTALL_UBUNTU.md),
[real Android testing](REAL_ANDROID_TESTING.md) and [remaining issues](KNOWN_ISSUES.md).
