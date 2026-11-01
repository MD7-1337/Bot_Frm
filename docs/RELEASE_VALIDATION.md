# Alpha recovery validation — 2026-11-01

Classification: **Alpha development**. Public binary redistribution is **BLOCKED**.
The repository is being recovered on `recovery/continue-alpha-2026-11-01` from
`d6e85dc9624ccd4ed238c51698c41dc583b6a6b1`. Main and previous feature branches are
preserved. Draft PR: https://github.com/MD7-1337/Bot_Frm/pull/4 (unmerged).

Build-specific identity is in `BUILD_INFO.json`, `PAYLOAD_INVENTORY.json` and
archive SHA-256 sidecars. This document records completed runs available before
this source snapshot; it does not pre-approve a later build.

## Verified native build milestone

Run https://github.com/MD7-1337/Bot_Frm/actions/runs/41300939150 built source
`bf0f7b10e9691a9a093f5f1c91d32be99695f35d` on Windows Server 2022 x64 and Ubuntu
22.04 x86-64. Actual results:

| Check | Result |
| --- | --- |
| Windows source | 961 passed, 2 failed, 3 skipped, 111.781 seconds |
| Ubuntu source | 963 passed, 0 failed, 3 skipped, 74.913 seconds |
| Local Ubuntu 24.04 source | 963 passed, 0 failed, 3 skipped, 99.01 seconds |
| Real Windows EXE, extracted ZIP relocation with spaces | PASS — frozen workflow |
| Windows installer | PASS — install, Start menu target, same-version reinstall, installed workflow, uninstall, external project preservation |
| Ubuntu extracted/relocated executable | PASS — frozen workflow |
| Same Ubuntu archive, clean 22.04 container, no Python, UID 65534 | PASS — frozen workflow |
| Public artifact upload | BLOCKED by dependency/application licensing gate |
| Physical one-phone/two-phone testing | NOT VERIFIED |

Each full suite includes 30 opt-in GUI cases. The three skips require optional
Tesseract executable/model availability. No failed case was skipped. The two
remaining Windows failures concern exact restored CRLF text comparison and
preview-pane geometry in the Windows offscreen fontless environment. Follow-up
changes correct source comparisons, bound the editor pane, and use the native
Windows Qt platform with a Segoe UI/font preflight. Native validation of that
follow-up must be checked separately before acceptance.

Frozen smoke exercises actual Monaco, spawned simulation workers, OpenCV image
matching, breakpoints/variables/stepping, recorder, scheduled execution, durable
history and project export/restore. The Windows installer is unsigned. Reinstall
over the same Alpha version is verified; a different-version upgrade and normal
interactive desktop/DPI/multiple-monitor testing remain unverified.

## Redistribution remains blocked

Actual payload inventories revealed unused Qt Charts/Data Visualization/Graphs
libraries collected via QML hooks. These GPL-only modules do not satisfy the
intended LGPL route. The follow-up specs exclude unused Python QML/Quick bindings
while preserving native dependency scanning; native frozen smoke and inventories
must confirm their absence. A local pruned Linux developer build passed frozen
smoke; it is not a cleared distribution package.

The FFmpeg/PyAV source build and exact ABI/decoder probes now pass on both native
platforms. Corresponding sources, configure options, generated VERSION metadata,
build script and installed-wheel correspondence are retained. This is separate
from completing Qt/Chromium notices, native dependency mapping and actual LGPL
replacement validation. The owner has not yet selected an application LICENSE.
See [dependency review](THIRD_PARTY_NOTICES.md).

GitHub Actions uploads source XML, frozen/installer smoke JSON, SHA-256 sidecars,
payload inventories and dependency evidence under `validation-<platform>-<SHA>`.
These artifacts contain **validation evidence only**, not the application EXE or
archive. Do not represent them as a Windows download. No GitHub Release is created.
Approved future application downloads require both source and redistribution gates.

Use [Windows setup](INSTALL_WINDOWS.md), [Ubuntu setup](INSTALL_UBUNTU.md),
[real Android acceptance](REAL_ANDROID_TESTING.md) and
[hardware checklist](HARDWARE_ACCEPTANCE.md). ADB/scrcpy/Tesseract remain explicitly
selected external tools; no USB permissions are changed automatically. The school
computer is not required. Physical phone results must remain NOT VERIFIED.

Historical evidence is preserved in
[the previous validation report](RELEASE_VALIDATION_2026-10-31.md).
