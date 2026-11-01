# Recovery checkpoint — 2026-11-01

Work only on `recovery/continue-alpha-2026-11-01`. Starting commit:
`d6e85dc9624ccd4ed238c51698c41dc583b6a6b1`. Original checkout was clean;
fetch confirmed the documented branch state. Main, the original workspace and
previous feature branches were not modified. Do not reset history.

Draft PR: https://github.com/MD7-1337/Bot_Frm/pull/4 (unmerged).
Verified source: `1e14932ea47bf174096fd62eda7a29e805c681c7`.
Native run: https://github.com/MD7-1337/Bot_Frm/actions/runs/41303947753
The following documentation/evidence commit does not change application code.

## Completed source acceptance

Both Windows Server 2022 x64 and Ubuntu 22.04 x86-64 full suites:
**975 passed, 0 failed, 3 skipped**, including **30 GUI cases each**.
Durations: Windows 125.589 seconds; Ubuntu 100.382 seconds.
All eight original Windows regression groups passed independently, including 15
adversarial archive variants and three strict timeout clock variants. Managed
project workflow additionally passed a separate repeat (13.750 and 12.097 seconds)
and the full suite. Skips require optional Tesseract executable/model availability.
No failed test was skipped, removed, renamed or xfailed. Source XML is preserved
under `validation/recovery-2026-11-01/final-source-*`.

The managed probe now requires a post-Home frame, settled input transform, visible
tap target and actual gesture delivery. Production stale-frame and resize input
cancellation remain unchanged. Windows headless tests explicitly load system
fonts; installed EXE smoke separately requires Qt's native Windows platform.

## Native package status

Read `RECOVERY_REPORT_2026-11-01.md` and `RELEASE_VALIDATION.md` for the final
package run, checksums, installer and clean-container evidence. Real Windows
EXE/ZIP/unsigned installer and Ubuntu portable builds have already passed actual
frozen workflow smoke in prior recovery runs; final source packaging is validated
separately. Never substitute a prior checksum for a newly rebuilt archive.

## Remaining release blockers and exact next steps

1. Resolve the owner's application distribution license and confirm rights to
   apply it. There is no application LICENSE file; none was invented.
2. Finish exact Qt/PySide/Chromium notice and corresponding-source evidence for
   deployed binaries. Qt wheel METADATA/WHEEL/RECORD are fingerprinted, but the
   audited wheels supplied no license texts. Versioned source URLs alone do not
   prove wheel/source correspondence or satisfy every source obligation.
3. Complete actual native-library license mapping, including OpenCV/NumPy native
   dependencies and the chosen Python/Windows runtime. Artifact inventories and
   SHA-256 values identify actual deployed files, rather than metadata alone.
4. Verify a practical LGPL-compatible replacement/relink procedure. Both native
   FFmpeg/PyAV source builds, exact ABI/decoder checks and installed-wheel hash
   correspondence already pass. Sources, build script and VERSION override
   provenance are retained. Do not switch back to an unsuitable stock wheel.
5. Keep unused GPL Charts/Graphs/DataVisualization/VirtualKeyboard absent. Both
   specs exclude unused Python QML bindings; the QtGui hook omits only the virtual
   keyboard plugin before native analysis while retaining host IMEs. The payload
   guard writes evidence then rejects reintroduction. This is not blanket license
   approval.
6. Keep binary uploads blocked until the above requirements are actually met.
   Current `validation-*` and `source-tests-*` Actions artifacts contain evidence,
   not an application download. GitHub-hosted workspaces are ephemeral: blocked
   binaries remain in the job workspace until teardown, not a persistent download.
   After clearance, rerun native builds and verify actual approved artifacts before
   providing download links. Do not create a public GitHub Release automatically.
7. Perform real Windows 10/11 desktop/DPI/standard-user acceptance and a genuine
   different-version installer upgrade. Current reinstall validation uses the
   same Alpha version. Unsigned builds are not production-signed releases.
8. Execute `REAL_ANDROID_TESTING.md` and `HARDWARE_ACCEPTANCE.md` on authorized
   machines with one and two phones. USB/Wi-Fi/scrcpy/real input/recognition,
   disconnect/reconnect/routing/isolation/emergency stop remain NOT VERIFIED.
   Do not alter host USB privileges automatically or require the school computer.

The embedded Qt Chromium credits page could not supply notices: Qt 6.8.3 returned
ERR_INVALID_URL for chrome://credits. No error page was accepted as license
material. Obtain and verify the actual corresponding source/notices instead.

For further code changes, repeat targeted tests then complete both native suites
and rebuild both packages. For notice/source changes, regenerate inventories and
package checksums. Keep this Alpha development until release blockers are closed.
