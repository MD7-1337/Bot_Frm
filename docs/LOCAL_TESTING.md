# Test the Phase 6 alpha on your computer

For the current source increment, use [installation and dependency
health](INSTALLATION.md) first. `python -m app.main --health` reports missing or
wrong-version packages, native imports, pinned Monaco files, disk space and
optional Android/OCR tools without opening the GUI. Settings exposes the same
background health check. A loader file merely existing is insufficient: the
editor now verifies all pinned files before loading and reports startup failures.

Windows 10/11 x64 is the final target. The current cloud validation ran on Linux,
not on Windows or your school computer. A working GUI does not grant USB access.
You confirmed that the original USB problem was on the PC; use the report below
to identify its exact restriction before changing phone/app settings repeatedly.

## Get this stacked change

Use a fresh directory so your existing scripts and checkout remain intact:

```bash
git clone --branch feat/phase6-recognition-simulator https://github.com/MD7-1337/Bot_Frm.git Bot_Frm-alpha
cd Bot_Frm-alpha
```

This branch starts from `fix/alpha-device-connect-and-ux-overhaul` (`7252f02`).
The stacked draft PR targets that previous Alpha branch. No merge into main is
needed to test it. All older reports are retained as historical evidence.

## Linux without sudo

If you already have uv and the Qt host libraries that let the previous app open:

```bash
uv sync --locked --extra test --python 3.12
.venv/bin/python tools/fetch_monaco.py
.venv/bin/python tools/fetch_adb.py
.venv/bin/python tools/fetch_scrcpy.py
bash tools/run-studio.sh
```

These commands install into the checkout/user environment. They do not request
sudo, change udev rules, install USB drivers or issue `adb kill-server`.
No `kill-server` command is issued. ADB itself can restart a server on a client/
server version mismatch, so avoid mixing different SDK copies of ADB.
Initial dependency/tool downloads require allowed internet access and disk space
(roughly 1 GB for the existing Python/Qt development environment on this cloud
host, plus caches). Use a directory where your account can execute programs.

If uv is unavailable and your system Python supports creating virtual environments:

```bash
python3 -m venv "$HOME/.local/share/aas-uv"
"$HOME/.local/share/aas-uv/bin/python" -m pip install "uv==0.12.23"
"$HOME/.local/share/aas-uv/bin/uv" sync --locked --extra test --python 3.12
```

Then run the three fetch commands and launcher above. If the school's Python
cannot create a venv, downloads/executables are blocked, or native Qt libraries
are missing, ask IT for the prerequisite. This application cannot bypass host
policy. The administrator library list is in [README_UBUNTU.md](../README_UBUNTU.md);
it is not an instruction to run sudo on a restricted school computer.

Do not add `QT_QPA_PLATFORM=offscreen` or disable the WebEngine sandbox for normal
desktop use. Those flags are for isolated headless cloud tests only.

## Windows source startup (not a Windows release)

With Python/uv available on a Windows 10/11 x64 desktop, in PowerShell:

```powershell
uv sync --locked --extra test --python 3.12
.venv\Scripts\python.exe tools\fetch_monaco.py
.venv\Scripts\python.exe tools\fetch_adb.py
.venv\Scripts\python.exe tools\fetch_scrcpy.py
.venv\Scripts\python.exe -m app.main
```

Alternatively run `tools\run-studio.ps1` when your account's normal script policy
allows it. Do not change execution policy just for this launcher; the direct
Python command works without a PowerShell script. Missing OEM USB drivers may
require your administrator. No Windows EXE/installer is delivered or validated.

## Start without a phone

Launch normally with `bash tools/run-studio.sh`, then **Start Demo Session** or
`Ctrl+Shift+D`. **Device Manager → Simulation** offers three scenarios, delay,
reset/stop and **Open scenario script**. Review/approve the example script and
Run it; real image recognition changes the local simulated screen. Capture/crop
and record/replay through the existing workspaces. See [SIMULATION.md](SIMULATION.md),
[RECOGNITION.md](RECOGNITION.md) and [RECORDER.md](RECORDER.md).

ADB and scrcpy downloads above are optional when exclusively using demos. No
USB permission fix is needed to use them. Tesseract is optional and never
auto-installed; without it image/color matching and every non-OCR demo still run.

The terminal-only fixture remains `.venv/bin/python -m examples.run_visual_fixture`.
A stateful terminal demo is `.venv/bin/python -m examples.run_simulation --scenario recorder`.
Neither is Android hardware verification.

## Connect a USB phone

1. Open **Device Manager** in the left sidebar (`Ctrl+2`). USB discovery runs
   automatically while the application is open; Refresh runs it immediately.
2. Use a USB **data** cable. Unlock the phone, enable Developer options and USB
   debugging, and approve this computer on the phone's authorization prompt.
   USB requires no Wi-Fi address and no Connect button.
3. Select the phone's card or its entry in the header device selector. Names
   and groups are labels; actions always use the actual ADB serial.
4. **Unauthorized:** unlock/approve the prompt. **Offline:** check cable/transport
   and refresh. **USB permissions denied / `????????????`:** the host cannot
   read the serial. Ask school IT for udev/group/device access; the application
   cannot fix that without host permission. **No device:** check data cable,
   phone mode, debugging, host visibility and driver/permission policy.
5. Choose **Open preview**. This now actually starts/reveals live video. Wait
   for a frame. A failure shows its reason; no static image is labeled as video.
   In a compact window, **Preview** in the header reveals/hides the phone pane.
6. Tap, double tap, hold or drag within the image. Home/Back target the selected
   idle phone. Manual input is disabled while its worker owns it or emergency
   stop is latched. Letterbox margins never send input.

## Diagnose a connection without a terminal

1. In Device Manager, click **Diagnose Connection**. Leave the video check enabled
   to test the complete preview path; turn it off only if you intentionally want
   that stage marked NOT VERIFIED.
2. The Diagnostics tab checks the selected ADB executable/path, version, server,
   device listing, authorization, a harmless Android query, screenshot decoding,
   and startup/receipt of a real decoded scrcpy frame. It does not tap the phone,
   issue `kill-server` or request elevated permissions. ADB's own version-mismatch
   behavior is described above.
3. Read the first **FAILED** stage and its next action. Later stages are **NOT
   VERIFIED**, not successful. With multiple phones select the intended one.
4. In **Settings → Devices & video**, choose a known ADB executable if the path
   is wrong. Source checkouts do not include downloaded binaries; the fetch
   commands above restore them. A saved explicit path is not silently replaced.
   `STUDIO_ADB` overrides saved ADB selection. Stop previews/runs and wait for
   pending jobs before changing tools, then Apply and diagnose again.
5. Choose **Copy Diagnostic Report**, leaving **Redact device serials** checked.
   Paste that short text when asking for help. Pairing codes are never recorded;
   copied reports also replace home-directory prefixes and known serials. A
   report contains no screenshot pixels. Review any text before sharing it.

Optional terminal equivalent, which also works without opening Qt Widgets:

```bash
bash tools/run-studio.sh --diagnose-connection
# If several phones are connected:
bash tools/run-studio.sh --diagnose-connection --serial YOUR_EXACT_SERIAL
# Intentionally skip video (reported NOT VERIFIED):
bash tools/run-studio.sh --diagnose-connection --no-video
```

Exit status 1 means at least one diagnostic stage failed, including no phone
being connected. It is not an application crash. `--diagnostics` prints installed
capabilities/paths; it is different from the staged connection check.

## Wi-Fi when permitted by the host/network

On Android 11+, open Wireless debugging and Pair device with pairing code. In
Device Manager's Connect tab, enter its **pairing** host:port and choose Pair….
Enter the six-digit code. Then replace the address with the separate **connection**
port shown by Wireless debugging and choose Connect. Pairing alone is not a
usable connection. The app confirms authorization and a device query before
showing a connected confirmation. Wrong ports, offline/unauthorized states and
blocked networks remain errors. Do not attempt to bypass school network policy.

Disconnect selected Wi-Fi affects only that host:port. Reconnect uses that exact
endpoint. USB reconnect means replug/check/authorize and refresh; it does not
restart ADB or change OS permissions. Old scripts/recordings never auto-resume.

## Capture and run your first visual script

1. Choose a project directory (File → Choose project image library, or the
   project explorer's Open… button), then select a connected phone.
2. Open **Visual Tools** (`Ctrl+3`), choose **Capture region…**, and drag a rectangle
   around a stable target. Save under `project/images/start.png` using **Save
   crop + insert reference…**. The editor receives ordinary Python text.
3. Test the selected crop on a new phone frame. The comparison view shows match
   scores and original Android coordinates and sends no input. Close the dialog.
4. Select an image in the library. Set threshold, explicit scales, offsets or
   search bounds if needed; test it on a fresh screen and insert a Pattern call.
   On smaller windows scroll the Target Inspector to its lower controls.
5. Open **Script Studio** (`Ctrl+1`). Use New to create a tab, then write:

   ```python
   print(device.serial)
   click("start.png")
   ```

6. Save inside the project, select the intended phone and choose Run/F5. Approve
   only code you trust; Python has your normal user permissions. Observe Output
   and events or **Activity & Logs**. Pause/F6, Resume/Shift+F6 and Stop/Shift+F5
   control the selected run. Current-line highlighting is not a full debugger.
7. For multiple phones, Ctrl-select their cards and use Execution → Run editor
   on selected phones. Assign Python files to current phones, then Run assigned
   files for different scripts. Each built-in context remains serial-bound.

**Emergency stop** is always in the header (`Ctrl+Shift+F12`). It blocks new studio
inputs and stops all workers. Reset explicitly using the toolbar/menu after the
stop completes. Already-dispatched Android input cannot be reversed.

## Record, save and replay

1. Select an idle authorized phone and open **Recorder** (`Ctrl+4`). Start on
   current phone, then use the preview's supported taps/holds/drags/Home/Back.
2. Pause/resume recording as needed, then Stop. Only successfully acknowledged
   studio controls for the recorded serial enter the timeline. Physical touches
   on the phone itself are not observed.
3. Edit a Python call, add a delay, reorder or delete steps. Insert Python into
   Monaco for richer conditions/loops, or save/open a JSON recorder session.
   Opening a session validates data and never executes it.
4. Choose Replay on selected phone and approve trusted execution. Check the
   phone and screen geometry first: reopening a session does not reconnect its
   recorded serial or scale its coordinates automatically. Normal workers run
   the generated Python, including pause/stop/emergency and disconnect behavior.

## Phone-free checks

```bash
.venv/bin/python -m examples.run_visual_fixture
```

This existing example creates explicit synthetic assets and runs fixture workers;
it does not open a physical phone or verify USB/video. Tests and screenshots label
all simulated devices. Real hardware remains necessary for the following gate.

## Local real-device acceptance checklist — NOT VERIFIED in cloud

- [ ] Record OS, ADB/Qt/Python/PyAV/server versions, phone model/Android and transport.
- [ ] USB discovery/authorization succeeds on this account, or diagnostics correctly
      identifies the host restriction. Confirm the actual serial selected.
- [ ] Live scrcpy frames update on the phone's changing screen; test rotation and
      reduced quality. Screenshot fallback must be labeled separately.
- [ ] Tap/double tap/hold/drag, Home/Back target only this phone; letterboxes do nothing.
- [ ] Capture/crop/save/insert/test a real target, run it, inspect output and stop.
- [ ] Record, edit, save/reopen and replay a supported workflow; check actual timing.
- [ ] Run two phones independently; disconnect one while the other continues.
- [ ] Reconnect explicitly; no old command/script/recording resumes automatically.
- [ ] Test emergency stop while running and during a failed connection; close
      during capture/video startup and verify cleanup.
- [ ] Repeat on Windows 10/11 with OEM drivers, actual DPI/monitor changes and
      native process spawning. CI does not replace physical driver/video tests.
