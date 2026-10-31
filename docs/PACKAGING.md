# Cross-platform developer distributions

`.github/workflows/cross-platform-alpha.yml` independently tests/builds Windows
Server 2022 x64 and Ubuntu 22.04 x86-64 candidates. It retains source JUnit,
public failed-test annotations, source commit manifests, checksums and frozen
smoke evidence. No stable release is published. Recipient instructions and actual
status are in [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md),
[INSTALL_UBUNTU.md](INSTALL_UBUNTU.md) and [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md).
Both archives are tested after extraction/relocation outside the source checkout.

The source version remains **0.2.0 Alpha**. The Windows build recipe and CI below
are implemented. A Linux source test does not establish that a Windows executable
works. No Windows ZIP or installer is created by adding these files; see the
current validation report for actual artifact and CI results.

Use a Windows x64 machine with Python 3.12 for building. A completed portable
payload bundles Python, PySide6/QtWebEngine, OpenCV, PyAV, NumPy, pinned IANA
timezone data and local Monaco. Bundled tzdata supplies timezone-aware schedules
on Windows, which does not provide the Unix system timezone database.
Recipients do not need system Python, Node or administrator privileges. OCR is
optional and external. Android platform-tools and scrcpy server are external by
default so the demo/editing package does not silently redistribute SDK downloads.

```powershell
uv sync --locked --extra test --python 3.12
uv pip install --python .venv/Scripts/python.exe PyInstaller==6.12.0
.venv/Scripts/python.exe tools/fetch_monaco.py
.venv/Scripts/python.exe tools/build_windows.py
```

The build validates every pinned Monaco asset, collects application submodules
and package metadata, uses the PyInstaller PySide6 hooks for Qt resources and
creates a directory distribution. It launches the **frozen** executable before
archiving it. That executable creates a temporary real demo project, spawns the
normal isolated worker, matches/clicks a template and verifies changed simulator
state. It then opens the real workbench and requires Monaco readiness. The smoke
disables phone discovery and executes only built-in demo source. Temporary
configuration and data are removed after the run.

Successful outputs:

- `dist/AndroidAutomationStudio/AndroidAutomationStudio.exe` and its runtime.
- `dist/windows-frozen-smoke.json` with actual worker/GUI/frozen evidence.
- `dist/AndroidAutomationStudio-windows-x64-portable.zip` and SHA256 sidecar.
- `dist/windows-build-manifest.json` with source commit and verification result.
- `build/release-notices/inventory.json` and preserved installed notices.

An existing ZIP is never overwritten. Move a previous artifact before rebuilding.
PyInstaller regenerates its `build/` and executable payload directory; do not
place projects there. User projects/configuration belong outside the payload.
The generated notices inventory is an engineering input to the release review,
not completed legal clearance. See [third-party review](THIRD_PARTY_NOTICES.md).

To intentionally include locally reviewed Android tools, first run the pinned
`fetch_adb.py` and `fetch_scrcpy.py` helpers on Windows, review the exact binaries
and required notices/SDK terms, then pass `--include-android-tools`. Runtime tool
selection retains explicit `STUDIO_ADB`/saved settings, then PATH/local fallback;
scrcpy validates its exact server digest. A packaged artifact must be tested with
the selected tools on physical hardware before claiming Android acceptance.

## Optional installer

After the portable payload passes on Windows, pass `--installer` to the builder
or compile `packaging/studio.iss` using installed Inno Setup 6. The script
creates a per-user installation, Start Menu shortcut, optional desktop shortcut,
uninstaller and stable application identity for upgrades. It never deletes user
projects/settings and does not require elevation. The builder never silently
installs a compiler; CI explicitly prepares its own machine. An installer is **NOT BUILT** until an
actual compiler run and installer acceptance are recorded.

## CI and remaining Windows gates

The cross-platform workflow retains both source and frozen results. A failed
source regression still allows a frozen package test for developer investigation;
the final acceptance gate marks that job failed. Package upload requires its
actual extracted smoke to pass. Accompanying evidence must be read before using
an artifact; its existence alone does not establish complete Alpha acceptance.
`tools/observe_actions.py` reads normal public Actions status pages where API
access is unavailable. Private logs/artifact downloads still require GitHub login.

Before a user release, test the extracted ZIP on a clean Windows 10/11 x64 machine
without Python/Node, offline; verify high-DPI rendering, GPU drivers, project
open/save/export, worker and debugger shutdown, optional OCR, and selected
ADB/scrcpy paths. Test actual installer install/upgrade/uninstall preservation if
an installer is built. Code signing, update verification and an updater are not
implemented. No self-update or network download occurs during normal startup.
