# Ubuntu portable application

**Current application downloads are blocked pending licensing clearance.** Native
Ubuntu 22.04 builds and clean no-Python frozen smoke have passed; `validation-*`
artifacts contain evidence only. See [current results](RELEASE_VALIDATION.md).

The Linux release build targets **Ubuntu 22.04 x86-64 (glibc 2.35)**. Its archive
contains Python 3.12, Qt/PySide6/WebEngine, Monaco, OpenCV/NumPy, PyAV, SQLite and
timezone data. It does not use a source checkout, virtual environment, Node.js,
AppImage or FUSE at application runtime. See `RELEASE_VALIDATION.md` for the
actual artifact checksum and platform test results; a recipe alone is not a pass.

Developers can reproduce the Ubuntu 22.04 build and clean-runtime test with
`bash tools/build_linux_docker.sh`. It uses a local Docker daemon, retains proxy
and registry configuration, and mounts a combined public CA bundle during network
build steps. Set `STUDIO_BUILD_CA_BUNDLE` when your trusted bundle is elsewhere.
No CA, credential, source checkout or virtual environment is copied into the
portable payload. The final test container has no system Python installed.

## Download, extract and start

Download `AndroidAutomationStudio-ubuntu-x86_64.tar.gz` and its
`.tar.gz.sha256` sidecar from the build artifact location in the release report.
Keep both files together, then run:

```bash
sha256sum --check AndroidAutomationStudio-ubuntu-x86_64.tar.gz.sha256
tar xzf AndroidAutomationStudio-ubuntu-x86_64.tar.gz
cd AndroidAutomationStudio
./run-studio.sh
```

Extract the entire directory. Moving it to a different user-owned location,
including one containing spaces, is supported. Do not copy only the executable
or delete `_internal`. Start as your normal desktop user; **do not use sudo**.
If a desktop file manager asks whether to trust an executable, follow your
computer's normal authorized workflow. There is no system installer or registry
change. Projects and configuration stay in user-owned locations, separate from
the application directory.

Choose **Start Demo Session** to work without a phone. Demo Mode and Monaco are
offline features once the archive is installed. Opening a downloaded project
does not grant execution permission: review scripts and imports before approving
them. Python runs with your user permissions, not inside an OS security sandbox.

## Host libraries and restricted computers

A normal Ubuntu desktop supplies many native graphics/audio libraries. The
build/runtime checks use these Ubuntu packages:

```text
libegl1 libgl1 libopengl0 libnss3 libnspr4 libasound2 libatomic1
libglib2.0-0 libfontconfig1 libfreetype6 libxi6 libxkbfile1
libxss1 libxtst6 libcups2 libpulse0
libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1
libxcb-image0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0
libxrandr2 libxdamage1 libxcomposite1 libx11-xcb1 libdbus-1-3
```

If the application reports a missing `.so` or Qt platform plugin, preserve that
error and ask the computer's administrator to install the supported host library,
or test on another authorized Ubuntu desktop. The app does not silently change
udev rules, group membership, kernel/user-namespace settings or school policies.
Do not disable WebEngine's sandbox to force ordinary desktop startup. Headless
CI test overrides are explicitly isolated in the build workflow.

## Android tools and connection

ADB and the pinned scrcpy 3.1 server are optional external components. They are
not required for editing or Demo Mode. In **Settings → Devices & video**, select
an existing trusted Android SDK platform-tools executable and the official
matching scrcpy server. The server's SHA-256 is checked. Source developers can
use the verified `tools/fetch_adb.py` / `tools/fetch_scrcpy.py` helpers; packaged
users can obtain the official tools using the links in the Windows/Android guide.
No binary or OCR language model is downloaded silently.

Connect a USB data cable, enable USB debugging and authorize on the phone.
Use **Device Manager → Diagnose Connection** before assuming a driver or app
defect. USB permission/udev restrictions need local administrator authorization;
the app cannot repair or bypass them. Properly configured Android wireless
debugging may provide an authorized alternative. See `REAL_ANDROID_TESTING.md`
for the one- and two-phone acceptance procedure.

## Local diagnostics

From the extracted directory:

```bash
./run-studio.sh --health-report "$HOME/studio-health.json"
./run-studio.sh --diagnose-connection --no-video
```

The GUI also provides dependency health and redacted connection diagnostics.
Review reports before sharing: scripts, paths and screenshots can contain private
information. Optional OCR needs a locally configured Tesseract executable and
language data. Missing OCR must not prevent ordinary image/color recognition.

For development-only headless verification, the frozen executable supports
`--release-smoke-report /a/writable/report.json`. Its report distinguishes frozen
runtime evidence from physical-phone and Windows acceptance. A passing demo does
not establish real USB, scrcpy video, DPI or multiple-monitor compatibility.
