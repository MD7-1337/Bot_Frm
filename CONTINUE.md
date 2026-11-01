# Continuation checkpoint

Continue on `recovery/continue-alpha-2026-11-01` only. Latest preserved
checkpoint: `c2a1354426bac0f3fed53b29011157f15c233879` (the tested application
source is `1e14932ea47bf174096fd62eda7a29e805c681c7`). Do not reset, force-push,
or modify `main`. Draft PR #4 remains open and unmerged:
https://github.com/MD7-1337/Bot_Frm/pull/4

## Completed and verified

- Latest native CI run: https://github.com/MD7-1337/Bot_Frm/actions/runs/41303947753
- Windows Server 2022 x64: 975 passed, 0 failed, 3 optional-Tesseract skips;
  30 GUI tests passed. Ubuntu 22.04 x86-64: 975 passed, 0 failed, 3 same
  optional-Tesseract skips; 30 GUI tests passed.
- All eight original Windows regression groups passed independently. Windows
  frozen EXE, portable ZIP, and unsigned installer were built and smoke-tested;
  Ubuntu portable was built and clean-container smoke-tested.
- Packages are **not downloadable**: binary upload remains blocked by the
  unresolved distribution review. CI validation/source-test artifacts are
  available from the run above; they contain evidence, not application binaries.
- No physical Android phone testing has occurred; hardware compatibility remains
  **NOT VERIFIED**.

Detailed test evidence, package checksums, installer results, and root-cause
notes are in [the recovery report](docs/RECOVERY_REPORT_2026-11-01.md) and
[the detailed continuation notes](docs/RECOVERY_CONTINUATION.md).

## Owner's application-license direction

The owner chooses **MIT for original application code, subject to verifying
licensing rights**. This records direction only: do not add an MIT license file
or claim the rights are verified until ownership/contributor rights are checked.
The MIT choice does not clear any third-party dependency or redistribution
obligations.

## Remaining blockers and next steps

1. Verify rights to license all original application contributions under MIT;
   then add the accurately scoped license and copyright notices.
2. Complete artifact-specific Qt/PySide/Chromium notices and corresponding-source
   evidence, plus the native dependency license map for OpenCV/NumPy, Python, and
   Windows runtime components.
3. Independently verify the LGPL replacement/relink path for the shipped
   FFmpeg/PyAV components. Existing native builds and ABI checks passed, but that
   does not itself establish compliance.
4. Keep binary redistribution blocked until these checks are evidenced. Then
   rebuild, regenerate inventories/checksums, rerun native acceptance, and only
   upload binaries when approved. Do not create a public GitHub Release.
5. Complete independent Windows 10/11 recipient-machine, DPI, standard-user, and
   different-version upgrade checks; current installer validation covered
   per-user install, same-version reinstall, preservation, and uninstall.
6. Run the one-phone and two-phone procedures in `docs/HARDWARE_ACCEPTANCE.md`
   and `docs/REAL_ANDROID_TESTING.md` on authorized hardware. Keep all physical
   device results marked NOT VERIFIED until then.

See `docs/RECOVERY_CONTINUATION.md` for implementation details and exact prior
evidence paths. Keep the project classified as Alpha development.
