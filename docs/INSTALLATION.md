# Source installation and dependency health

Use a separate checkout and its own `.venv`; Python 3.12 is required. Do not
link another project's Python environment or Monaco directory. The Python
dependencies remain pinned in `uv.lock` and `pyproject.toml`.

On Linux, from the repository root:

```bash
uv sync --locked --extra test --python 3.12
.venv/bin/python tools/fetch_monaco.py
.venv/bin/python -m app.main --health
.venv/bin/python -m app.main
```

On Windows PowerShell:

```powershell
uv sync --locked --extra test --python 3.12
.venv\Scripts\python.exe tools\fetch_monaco.py
.venv\Scripts\python.exe -m app.main --health
.venv\Scripts\python.exe -m app.main
```

`uv sync --python 3.12` selects the intended interpreter independently of an
unrelated active pyenv version. Use the explicit `.venv` command to launch.
`--health` prints a JSON report and returns a nonzero status when a required
dependency is missing, the version is wrong or a native import fails. It can
run even when PySide6 and scientific dependencies are absent. It does not
connect a phone, start an ADB server, download packages or change host permissions.
The Settings dependency-health button runs the same checks in the background.

For physical phones, install the optional verified tools:

```bash
.venv/bin/python tools/fetch_adb.py
.venv/bin/python tools/fetch_scrcpy.py
```

Use the corresponding Windows `.venv\Scripts\python.exe` commands there. Missing
ADB or scrcpy is reported separately and does not block Demo Mode. ADB is checked
with `adb version`, not by sending commands to a device. The scrcpy server must
match the pinned official 3.1 SHA-256; selecting a different version is an error.
External ADB executable configuration remains available in Settings or `STUDIO_ADB`.
`STUDIO_SCRCPY_SERVER` selects an explicit local server file. Optional OCR checks
the configured Tesseract executable; the application does not download OCR models.

## Limited storage and restricted computers

Allow at least 1.5 GB for first-time Python/Qt setup plus cache storage; actual
space varies by platform. `tools/setup.sh` checks available application-volume
space before a fresh installation, and the Monaco fetcher requires 100 MB for
download/extraction and atomic replacement. If storage fills during installation,
select another user-owned volume and run setup there. No cleanup command or
automatic removal of unrelated files is part of setup.

Reuse uv's package cache across checkouts with `UV_CACHE_DIR` on a volume you
own; uv's default is the user cache. Monaco archives can similarly be shared
with `STUDIO_DOWNLOAD_CACHE`. Existing correct Monaco files are verified and
reused without downloading. Downloaded archives are checked against the pinned
SHA-512; all 105 installed distribution files are checked against source-controlled
SHA-256 hashes on editor startup. A partial, corrupt or wrong-version vendor
directory produces a precise repair command instead of a ready editor.

Do not replace these directories with symbolic links. A self-referential link
is rejected, and the fetcher refuses to delete or replace a symbolic-linked
vendor directory. Preserve any unrelated files before correcting such a setup.
The supported repair is to run this checkout's Python and `tools/fetch_monaco.py`.

Normal startup requires no sudo or administrator rights. Qt still needs native
host libraries. On Linux these commonly include the X11/XCB, xkbcommon, OpenGL,
font and NSS dependencies listed in [README_UBUNTU.md](../README_UBUNTU.md).
A wheel installation cannot supply every operating-system library. If native
imports fail on a school-managed machine, use the reported library name with
IT or a supported user environment. The app does not bypass the machine's policy.
Do not disable Chromium's sandbox for ordinary desktop use. Headless test flags
in [LOCAL_TESTING.md](LOCAL_TESTING.md) are specific to isolated test infrastructure.

Windows packaging and hardware acceptance are separate release gates. A passing
Linux dependency check is not evidence that the Windows portable build, installer,
USB driver or physical-phone workflow has been validated.
