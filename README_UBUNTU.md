# Android Automation Studio 0.2.0 — Ubuntu 22.04 x86_64

For the latest unmerged alpha fixes, clone with
`--branch feat/phase6-recognition-simulator` (used below).
If your school computer has no sudo access, start with
[LOCAL_TESTING.md](docs/LOCAL_TESTING.md). It requires no privileged commands;
host USB/driver/Qt library restrictions still need your administrator where applicable.

This project contains the current application, custom Monaco integration,
documentation, examples, tests, `pyproject.toml`, `uv.lock`, and an exported,
hashed `requirements.txt`. Generated `.venv`, caches, egg-info/build outputs,
downloaded `editor_web/vendor` assets and `.tools` binaries are not tracked. The
commands below restore those pinned dependencies without changing application
functionality. Internet access is needed for initial setup; core use is offline.

Current test results are in [PHASE6_VALIDATION.md](docs/PHASE6_VALIDATION.md).
The cloud machine was not Ubuntu 22.04. These are Ubuntu installation instructions, not a
claim of an Ubuntu or physical-phone acceptance test. The binary ADB dependency's
glibc baseline was inspected and is compatible with Ubuntu 22.04's glibc baseline;
actual USB/device behavior still needs your testing.

## 1. Clone into a fresh directory

```bash
sudo apt-get update
sudo apt-get install -y git
mkdir -p "$HOME/Applications"
git clone --branch feat/phase6-recognition-simulator https://github.com/MD7-1337/Bot_Frm.git "$HOME/Applications/android-automation-studio-0.2.0"
cd "$HOME/Applications/android-automation-studio-0.2.0"
```

Use a fresh target directory so existing projects are preserved.

## 2. Install Ubuntu desktop libraries and uv

Run these as your normal desktop user, using sudo only for apt. Ubuntu 22.04 uses
`libasound2` and `libglib2.0-0` (not the newer `t64` package names).

```bash
sudo apt-get install -y python3-venv ca-certificates \
  libatomic1 libgl1 libegl1 libgbm1 libdrm2 \
  libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libasound2 \
  libfontconfig1 libfreetype6 fonts-dejavu-core \
  libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 libxrender1 \
  libxrandr2 libxtst6 libxi6 libxshmfence1 libxkbfile1 \
  libxkbcommon0 libxkbcommon-x11-0 \
  libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-randr0 libxcb-render0 libxcb-render-util0 libxcb-shape0 \
  libxcb-shm0 libxcb-sync1 libxcb-util1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1

python3 -m venv "$HOME/.local/share/aas-uv"
"$HOME/.local/share/aas-uv/bin/python" -m pip install "uv==0.12.23"
```

The small bootstrap environment installs uv without modifying Ubuntu's system
Python. Python 3.10, normally supplied by Ubuntu 22.04, is not the app runtime.
uv obtains the required Python 3.12 automatically when it is not already present.

## 3. Install the locked project and pinned runtime assets

```bash
cd "$HOME/Applications/android-automation-studio-0.2.0"
"$HOME/.local/share/aas-uv/bin/uv" sync --locked --extra test --python 3.12
.venv/bin/python tools/fetch_monaco.py
.venv/bin/python tools/fetch_adb.py
.venv/bin/python tools/fetch_scrcpy.py
.venv/bin/python -m app.main --diagnostics
```

These install Python dependencies into this checkout's `.venv`, local Monaco
0.52.2 assets, development platform-tools 37.0.1 and the exact scrcpy 3.1 Android
server. Download helpers verify their pinned integrity/checksum values and keep
TLS verification enabled. Node/npm and the native scrcpy desktop application are
not required. Do not run `sudo pip`, `sudo uv`, or launch the GUI with sudo.

Use the direct commands above on your machine. The retained cloud helper
`tools/setup.sh` defaults its cache to `/workspace/.cache/uv`; if you prefer that
helper, first set a user-owned cache:

```bash
export UV_CACHE_DIR="$HOME/.cache/uv"
export PATH="$HOME/.local/share/aas-uv/bin:$PATH"
bash tools/setup.sh
```

`pyproject.toml` and `uv.lock` are authoritative. The exported `requirements.txt`
contains hashed application/test dependency pins for Python 3.12; it excludes the
editable project itself. If you already have a Python 3.12 environment and use
pip instead of uv, install with `python -m pip install --require-hashes -r
requirements.txt`, then `python -m pip install --no-deps -e .`. Still run the three
asset download helpers. The uv workflow is recommended.

## 4. Start the integrated offline demo

```bash
.venv/bin/python -m app.main
```

Click **Start Demo Session** or press `Ctrl+Shift+D`. Choose the image, wait or
recorder scenario in **Device Manager → Simulation**. This uses the real Qt,
Monaco, OpenCV and spawned-worker application with locally simulated screens.
See [SIMULATION.md](docs/SIMULATION.md). No phone, ADB/scrcpy download or OCR
installation is needed for demos once Python/Qt/Monaco are ready. OCR is an
optional configured local executable; see [RECOGNITION.md](docs/RECOGNITION.md).

## 5. Run the terminal-only phone-free visual fixture

```bash
cd "$HOME/Applications/android-automation-studio-0.2.0"
.venv/bin/python -m examples.run_visual_fixture
```

This generates temporary known PNGs, executes both short-function and explicit
`device` APIs in separate actual worker processes, checks the results, and exits.
Expected final line:

```text
Both visual scripting styles completed in independent mock-device workers.
```

It requires no phone, USB debugging or display. It does not prove phone control.

## 5. Launch the desktop application

From a terminal in your normal logged-in Ubuntu graphical desktop:

```bash
cd "$HOME/Applications/android-automation-studio-0.2.0"
.venv/bin/python -m app.main
```

Do not copy the cloud's `QT_QPA_PLATFORM=offscreen` or browser-sandbox overrides
into normal desktop startup. If those were set in the current terminal, clear them:

```bash
unset QT_QPA_PLATFORM QTWEBENGINE_DISABLE_SANDBOX QTWEBENGINE_CHROMIUM_FLAGS
.venv/bin/python -m app.main
```

Without a connected phone, the GUI/editor still starts and reports that no
devices are available. To work with real targets, choose a project directory,
enable/authorize Android USB debugging, refresh devices, and start a preview.
The scripting API and run controls are documented in `docs/SCRIPTING_API.md`.

## 6. Tests

Core tests, with display-dependent GUI integrations intentionally skipped:

```bash
.venv/bin/python -m pytest -q
```

Complete suite from your normal graphical desktop, including real Monaco/Qt:

```bash
STUDIO_GUI_TESTS=1 .venv/bin/python -m pytest -q
```

Do not describe skipped GUI checks as passing. No real-phone test is implied by
either command. Phone/device instructions and known limitations are in
`docs/SCRIPTING_ENGINE.md` and `docs/STREAMING.md`.

## 7. Optional Android USB access on Ubuntu

Start with the bundled, verified ADB:

```bash
.tools/platform-tools/adb version
.tools/platform-tools/adb devices -l
```

If Ubuntu reports USB permission problems, install the distro udev rules and
grant your normal account the device group, then log out and log in again:

```bash
sudo apt-get install -y android-sdk-platform-tools-common
sudo usermod -aG plugdev "$USER"
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug/replug the phone, unlock it and accept its USB-debugging authorization
prompt. An `unauthorized` row means authorization is still needed on the phone.
Do not run the application as root to bypass USB permissions.

## Troubleshooting

- Missing Qt xcb/platform library: rerun the shared-library installation above;
  `QT_DEBUG_PLUGINS=1 .venv/bin/python -m app.main` prints plugin diagnostics.
- `Monaco assets missing`: run `.venv/bin/python tools/fetch_monaco.py`.
- Server checksum/version mismatch: use `tools/fetch_scrcpy.py`; arbitrary server
  versions are deliberately rejected. Do not disable checksum or TLS checks.
- No graphical display: run the phone-free fixture first; launch the GUI from
  your logged-in Ubuntu desktop rather than a bare SSH terminal.
- Python version error: use the explicit uv command above with `--python 3.12`.
