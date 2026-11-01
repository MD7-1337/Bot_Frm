# Alpha recovery validation — 2026-11-01

**Both native source suites and actual Windows/Ubuntu package smoke tests pass.
Application downloads remain BLOCKED by unfinished redistribution requirements.**
Classification: **Alpha development**, not Beta or Stable.

Verified source/build commit: `1e14932ea47bf174096fd62eda7a29e805c681c7` on
`recovery/continue-alpha-2026-11-01`. The subsequent evidence commit changes
only documentation. [Draft PR #4](https://github.com/MD7-1337/Bot_Frm/pull/4)
is unmerged; main and previous feature branches remain untouched.

Actual run: https://github.com/MD7-1337/Bot_Frm/actions/runs/41303947753

| Validation | Actual result |
| --- | --- |
| Windows Server 2022 x64 source | 975 passed, 0 failed, 3 skipped; 30 GUI cases; 125.589 s |
| Ubuntu 22.04 x86-64 source | 975 passed, 0 failed, 3 skipped; 30 GUI cases; 100.382 s |
| Eight independent Windows regression groups plus managed repeat | 25 passed, 0 failed, 0 skipped |
| Real Windows EXE and relocated ZIP with spaces | PASS — frozen workflow |
| Installed EXE using native Windows Qt platform | PASS — frozen workflow, qt_platform=windows |
| Unsigned per-user installer | PASS — install, shortcut target, same-version reinstall, uninstall and external project preservation |
| Ubuntu extracted/relocated portable | PASS — frozen workflow |
| Same Ubuntu archive, clean Ubuntu 22.04 without system Python, UID 65534 | PASS — frozen workflow |
| Excluded unused GPL Qt modules | Zero flagged paths in both actual inventories |
| Application artifact download | BLOCKED — validation artifacts contain evidence only |
| Physical one/two-phone testing | NOT VERIFIED |

The three skips per platform require optional Tesseract availability. No failed
case was skipped, removed, renamed or xfailed. Both final jobs fail solely at the
intentional binary redistribution gate; source/build/package acceptance passed.

Read the [complete recovery report](RECOVERY_REPORT_2026-11-01.md) for every
Windows root cause, changed file, exact test evidence, actual archive checksums,
installer limits, license findings and download status. The [package manifest](validation/recovery-2026-11-01/final-package-manifest.json)
and `native-final-*` evidence directories identify actual deployed payloads.

No application LICENSE was invented. Exact Qt/Chromium correspondence/notices,
complete native dependency mapping and LGPL replacement validation remain open.
See [third-party review](THIRD_PARTY_NOTICES.md) and
[continuation instructions](RECOVERY_CONTINUATION.md). Blocked binaries were
built in ephemeral CI workspaces and were not uploaded as persistent downloads.

Normal Windows 10/11 desktop/DPI/standard-user acceptance, a different-version
installer upgrade and physical phone behavior remain unverified. Use
[Windows setup](INSTALL_WINDOWS.md), [Ubuntu setup](INSTALL_UBUNTU.md),
[real Android testing](REAL_ANDROID_TESTING.md) and
[hardware acceptance](HARDWARE_ACCEPTANCE.md). The restricted school PC is not
required. ADB/scrcpy/Tesseract are external selections; no USB permissions are
changed automatically.

Historical evidence is preserved in the
[previous validation report](RELEASE_VALIDATION_2026-10-31.md).
