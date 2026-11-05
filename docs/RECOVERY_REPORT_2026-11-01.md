# Android Automation Studio — recovery report, 2026-11-01

**Real native Windows EXE/ZIP/unsigned installer and Ubuntu portable builds passed
frozen workflow validation. Both full source suites pass. Application downloads
remain BLOCKED by unfinished redistribution requirements.** Classification remains
**Alpha development**, not Beta or Stable, and physical Android is NOT VERIFIED.

## Git and recovery

- Working branch: `recovery/continue-alpha-2026-11-01`.
- Starting commit: `d6e85dc9624ccd4ed238c51698c41dc583b6a6b1`; checkout was clean.
- Verified source/build commit: `1e14932ea47bf174096fd62eda7a29e805c681c7`, pushed successfully.
- The subsequent report/evidence commit changes documentation only; its exact SHA
  is the recovery branch HEAD and is supplied in the final delivery message.
- Draft PR: https://github.com/MD7-1337/Bot_Frm/pull/4, targeting the verified
  ancestor `feat/cross-platform-alpha-release`; unmerged.
- Main, previous feature branches and the original offline workspace were not
  modified. No reset, force push, branch deletion, merge or GitHub Release occurred.

## Source validation and original Windows failures

Native run: https://github.com/MD7-1337/Bot_Frm/actions/runs/41303947753

| Platform | Passed | Failed/error | Skipped | JUnit duration | GUI cases |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows Server 2022 x64 | 975 | 0 | 3 | 125.589 s | 30 passed |
| Ubuntu 22.04 x86-64 | 975 | 0 | 3 | 100.382 s | 30 passed |

The three skips on each platform are `tests/test_ocr.py` lines 60, 75 and 94:
optional Tesseract executable/model availability. Image/color recognition runs
without OCR. No failed case became skipped, xfailed, deleted or renamed.

Every original Windows group ran independently before the full suite. The
managed-project case also passed a second separate run. The independent groups
plus repeat total **25 passed, 0 failed, 0 skipped**. Exact XML is under
[final Windows source evidence](validation/recovery-2026-11-01/final-source-windows/)
and [Ubuntu source evidence](validation/recovery-2026-11-01/final-source-ubuntu/).

| Original failure | Root cause and correction | Files changed | Independent Windows evidence |
| --- | --- | --- | --- |
| Managed project GUI | Dialogs completed; universal-newline comparisons disagreed with Monaco CRLF. Compare exact saved/restored UTF-8 bytes. A later intermittent recorder tap used fixed sleep before asynchronous frame/layout readiness; require post-Home frame, settled transform, visible point and actual gesture delivery. | `tests/probe_alpha_completion.py`; common preview/layout fixes below | `windows-regression-0.xml`: 1 passed, 13.750 s; `windows-regression-managed-repeat.xml`: 1 passed, 12.097 s; also full-suite pass |
| Debugger dynamic breakpoints | Windows bdb canonicalizes filename case; frozen linecache could miss and inspect edited disk source. Cache approved snapshot under bdb.canonic and retain isolation. | `app/automation/debugger.py`, `tests/test_debugger.py` | `windows-regression-1.xml`: 1 passed, 0.531 s |
| Multi-device workbench | Fixture required POSIX spelling of a native Windows path. Validate parsed image-reference identity using native Path resolution. | `tests/probe_device_workbench.py` | `windows-regression-2.xml`: 1 passed, 2.885 s |
| Simulator/recorder GUI | Preview controls and editor preferred width could overflow; Windows offscreen had no system font database. Full-width controls, shrinkable editor and system-font preflight restore usable geometry. Recorder image conversion must preserve the actual pixel offset rather than assume exact crop center. | `app/ui/live_panel.py`, `app/ui/shell.py`, `tests/probe_phase6.py`, workflow | `windows-regression-3.xml`: 1 passed, 9.868 s |
| Unsafe archive backslash | Import validator already rejected raw backslashes; Windows ZIP writer normalized the malicious fixture before import. Preserve raw ZIP member spelling; add drive/UNC/traversal/NUL adversaries and reject NUL-truncated original names. | `app/projects/management.py`, `tests/test_project_management.py` | `windows-regression-4.xml`: all 15 variants passed, 0.344 s |
| Recovery timeout | Rounded absolute deadline subtraction could exceed policy by an ulp. Clamp remaining time to original policy budget; keep strict bound assertions. | `app/automation/recovery.py`, `tests/test_recovery_engine.py` | `windows-regression-5.xml`: all 3 clock variants passed, 0.234 s |
| Windows pipe fail-closed | Fault injector missed native broken-pipe exceptions from both poll and recv. Inject requested unexpected error on both native paths. Production unexpected-error fail-closed logic retained and verified. | `tests/test_runtime.py` | `windows-regression-6.xml`: 1 passed, 0.424 s |
| Visual workspace GUI | Fixture attempted a double-quote filename forbidden on Windows. Use an apostrophe/Unicode fixture while preserving escaping and capture assertions. | `tests/probe_visual_workspaces.py` | `windows-regression-7.xml`: 1 passed, 2.344 s |

Other saved-source comparisons were corrected in `probe_alpha_ux.py` and
`probe_script_project_ui.py`. Three local repeated managed journeys passed
11.70/11.24/10.84 seconds before the native repeat. Earlier failures are retained
in the source history/evidence; they are not presented as accepted builds.

Windows source tests use Qt offscreen with `C:/Windows/Fonts`, checked Segoe UI and
Latin glyphs. Qt's [offscreen implementation](https://raw.githubusercontent.com/qt/qtbase/v6.8.3/src/plugins/platforms/offscreen/qoffscreenintegration.cpp)
uses FreeType on Windows; [fontDir](https://raw.githubusercontent.com/qt/qtbase/v6.8.3/src/gui/text/qplatformfontdatabase.cpp)
reads `QT_QPA_FONTDIR`. Native desktop tests otherwise clamp large test windows
to the runner's small display. Compact-layout assertions remain enabled. The
installed EXE smoke separately **requires `qt_platform: windows`**. Production
browser security defaults were not disabled.

## Actual Windows application and installer

| Deliverable/check | Result |
| --- | --- |
| `AndroidAutomationStudio.exe` built | YES — 5,060,234 bytes, native PyInstaller Windows executable |
| Portable ZIP built | YES |
| Inno Setup installer built | YES — unsigned |
| Extracted/relocated EXE, path with spaces | PASS, frozen=true |
| Installed EXE with native Windows Qt platform | PASS, frozen=true, qt_platform=windows |
| Install, Start menu target, same-version reinstall, uninstall | PASS |
| External user-project marker preserved | PASS |
| Different-version upgrade; manual Windows 10/11 desktop/DPI/standard-user acceptance | NOT VERIFIED |
| Approved application artifact download | NO — redistribution gate remains blocked |

Executable SHA-256: `caea8139f52a10bc4146bdcaf58fe11c1fbc99f9231a0e3f384708694673a0f7`.
Keep `_internal` beside the EXE; the portable ZIP contains its required runtime.
The core Python/Qt/runtime is bundled, and frozen execution outside the checkout
is verified. A clean Windows 10/11 recipient machine without Python has not been
independently exercised; that practical acceptance remains pending. Android/OCR tools are
external by default and selected explicitly; they are not silently bundled.

Frozen smoke actually exercised startup/Monaco, spawned simulation execution,
OpenCV recognition, breakpoints/variables/stepping, recorder, scheduled worker,
project export/restore and durable history. Shutdown had to complete owned
resource cleanup. The source GUI journey additionally closes/reopens the
workbench and verifies persisted history plus revoked task trust. A separate
cross-process frozen persistence/restart journey and interactive diagnostics CLI
acceptance were not independently added in this recovery; do not overstate them.

## Ubuntu application

Ubuntu 22.04 x86-64 portable built and passed extracted relocation with spaces.
The same SHA-verified archive passed in a clean Ubuntu 22.04.5/glibc 2.35 container
without a system python/python3 command, as UID/GID 65534. The frozen workflow
covers the same Monaco/simulation/recognition/debugger/recorder/scheduler/project/
history checks. Both actual inventories contain zero flagged unused GPL Qt paths:
Windows 1257 records; Ubuntu 1467 records.
Container-only headless sandbox override is not exported by the distributed
launcher. No USB privileges or host rules were changed.

## Checksums and downloadable evidence

These are checksums of real built packages, **not currently available application
downloads**. Binaries were retained in the CI workspace during validation but not
uploaded; GitHub-hosted workspaces are ephemeral after job teardown.

```text
AndroidAutomationStudio-windows-x64-portable.zip
6cd1ca4733e97d29bdcc92323619e6f8f740e1efe3582cb517a1ec2dccd42d52

AndroidAutomationStudio-windows-x64-setup.exe
d492f560b5f288b6346eb3221b17d731ba983a28ab78386c3362c0f76bb397b6

AndroidAutomationStudio-ubuntu-x86_64.tar.gz
9ed96cd8e4b9ff0751ec2b265b50d23fd654a632f6c36b194d1a3009bf8644e8
```

[Derived package manifest](validation/recovery-2026-11-01/final-package-manifest.json)
combines actual native checksums, source identity and payload evidence. The
Windows build manifest, per-file inventories, source-built LGPL provenance,
frozen reports, installer report and source XML are preserved under
`validation/recovery-2026-11-01/native-final-*`.

Open [the actual run](https://github.com/MD7-1337/Bot_Frm/actions/runs/41303947753) and sign in to GitHub to download:

- `validation-windows-x64-1e14932ea47bf174096fd62eda7a29e805c681c7`
- `validation-ubuntu-x86_64-1e14932ea47bf174096fd62eda7a29e805c681c7`
- `source-tests-windows-x64-1e14932ea47bf174096fd62eda7a29e805c681c7`
- `source-tests-ubuntu-x86_64-1e14932ea47bf174096fd62eda7a29e805c681c7`

These artifacts contain **evidence only**. Both final job conclusions are
**failure solely at the intentional binary redistribution gate**; source
acceptance, builds and package tests passed. No binary artifact or public release
was uploaded. After real clearance, rerun builds and verify approved
`AndroidAutomationStudio-<platform>-<SHA>` artifacts before giving download links.

## Licensing and remaining obligations

Verified evidence includes Python 3.12 runtime identity (Windows 3.12.10; Linux
3.12.15), PySide6/Shiboken/Qt 6.8.3 package records, Monaco 0.52.2 verified archive
notices, OpenCV 4.11.0.86, NumPy 2.2.4, tzdata 2026.6, PyAV 14.2.0 and source-built
FFmpeg 7.1. PyInstaller notices and available CPython license text are retained.
The installed Linux Qt query observed Chromium 122.0.6261.171. Per-build Qt
information is generated inside packages; source URLs are candidates, not proof
of corresponding source. This inventory is not a blanket license approval.

Both native LGPL builds pass exact seven-library ABI checks, LGPL configuration
checks and actual H264 decoding. The builder fixed MSYS2's actual installation
path and FFmpeg's accidental inheritance of the enclosing repository Git version.
The recorded VERSION override, original sources, build script and installed-wheel
native hashes are retained. Unused GPL Charts/Graphs/DataVisualization/Virtual
Keyboard collection is blocked; host keyboard/IME plugins remain.

**Redistribution remains BLOCKED** for these reasons:

1. No owner-selected application LICENSE or rights confirmation. This decision
   was requested; none was invented.
2. Exact Qt/PySide/Chromium notices and corresponding-source evidence are still
   incomplete. The audited Qt wheels supplied no license text files. An attempted
   embedded credits-page extraction returned ERR_INVALID_URL and was not accepted.
3. Full artifact-specific native dependency license mapping and source/notice
   obligations remain incomplete, including dependencies inside OpenCV/NumPy,
   Python and native Windows runtime components.
4. A practical LGPL replacement/relink procedure has not been independently
   validated for the complete Qt/PySide/FFmpeg payload.

See [third-party review](THIRD_PARTY_NOTICES.md) and
[continuation instructions](RECOVERY_CONTINUATION.md). Successful builds and
metadata do not authorize public binaries. Further developer builds can retain
`dist` on a controlled native build machine; this run does not provide a private
persistent binary-download service or claim legal clearance for redistribution.

## Real Android acceptance

Without phones, all source/frozen simulation workflows above can be tested.
Physical tests remain **NOT VERIFIED** and must use authorized machines:

- One phone: USB authorization, actual detection/state/version, moving scrcpy
  preview/rotation, serial-specific tap/swipe, screenshots/recognition, trusted
  Python, recorder/debugger/scheduler, disconnect/reconnect and emergency stop.
- Two phones: distinct previews/serials, independent simultaneous workers,
  correct routing, failure/disconnect isolation, and emergency stop for both.
- Configure actual ADB and matching scrcpy 3.1 server in Settings. Use Connection
  Wizard and redacted diagnostic export. Distinguish unauthorized/offline/USB
  permission failures. Android 11+ Wi-Fi pairing and connection use separate
  ports; pairing codes must not enter reports. Do not change host USB privileges
  automatically. The school computer is not required.

Follow [real Android testing](REAL_ANDROID_TESTING.md) and
[hardware acceptance](HARDWARE_ACCEPTANCE.md). The project is **Alpha development**:
functional native automated packages are verified, but approved binary delivery,
licensing and physical/interactive acceptance remain unfinished.
