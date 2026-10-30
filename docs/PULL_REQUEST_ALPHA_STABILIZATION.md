# fix: stabilize alpha connectivity and redesign automation workspaces

**Draft stacked PR. Base: `feat/device-manager-visual-tools`. Head:
`fix/alpha-device-connect-and-ux-overhaul`. Leave both branches unmerged for user review.**

The alpha launched but did not help users distinguish PC USB access problems
from application failures, and its competing docks/toolbars hid key workflows.
The user clarified that their original USB problem was on the PC. This change
adds actionable diagnostics and a substantial workspace redesign; it does not
claim that the school PC or a physical phone was repaired/verified from cloud.

## Implemented repairs

- Retain ADB `???????????? no permissions` entries as visible, unroutable diagnostic
  rows instead of incorrectly showing no device. Keep exact-serial controls and
  connection generation invalidation.
- Diagnose executable/path, version, server response, discovery/state, harmless
  Android query, original PNG decoding and scrcpy startup/real decoded frame.
  Failed later stages stay NOT VERIFIED; copied reports default to redaction.
- Saved ADB/server paths, `~` expansion, actual missing-binary feedback, separate
  pairing/connection ports and device-query confirmation before Wi-Fi success.
  No app command issues kill-server or tries privileged OS permission changes.
- Open preview now actually starts/reveals the selected managed stream. Controls
  reflect phone/editor/run/recording prerequisites; failures remain visible.
- Replace competing dock layout with real central workspaces, collapsible sidebar,
  device selector, contextual controls, persistent splitters and always-present stop.
  Add script tabs/project explorer, command search and consistent light/dark Qt
  and Monaco appearance, Settings, Activity & Logs and honest scheduling roadmap.
- Integrate existing capture/crop/library/Pattern testing and trusted execution.
  Add recorder JSON save/open, explicit delay editing and safe trusted-worker replay.
- Add serial-bound fresh RGB `getPixel`/`findColor` APIs, parent-process metrics,
  portable launchers/config isolation and Windows/Linux source CI configuration.

Python/PySide6, Monaco/QWebChannel restrictions, ADB, pinned scrcpy/PyAV transport,
OpenCV, process isolation, independent device contexts and emergency stopping
remain. No installer or new runtime dependency was added.

## Files and control audit

The [implementation/root-cause report](https://github.com/MD7-1337/Bot_Frm/blob/fix/alpha-device-connect-and-ux-overhaul/docs/ALPHA_STABILIZATION.md)
contains the full grouped inventory and limits. New app modules cover connection
diagnostics, theme/components/shell, script tabs/project explorer, settings,
parent metrics and RGB recognition. Existing UI/controller, ADB, editor and API
integration modules are updated. New tests/probe, launchers, source CI and user
instructions accompany the changes; GUI test settings are isolated across OSes.

The [functional inventory](https://github.com/MD7-1337/Bot_Frm/blob/fix/alpha-device-connect-and-ux-overhaul/docs/CONTROL_INVENTORY.md)
classifies all exposed controls and distinguishes fixture verification from
physical acceptance. [Local testing instructions](https://github.com/MD7-1337/Bot_Frm/blob/fix/alpha-device-connect-and-ux-overhaul/docs/LOCAL_TESTING.md)
cover Linux without sudo, intended Windows startup and the real-device checklist.

## Validation

**620 passed, 0 failed, 0 skipped; 32.68 seconds; exit 0** on Linux x86-64,
Python 3.12.14 / PySide6 6.8.3. The original 569 cases remain; 51 additional
collected cases include diagnostics, visible controls, recorder sessions and RGB API contracts.

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu \
STUDIO_CONFIG_DIR=/tmp/aas-alpha-final-regression .venv/bin/python -m pytest -q
```

These browser flags are only for this isolated headless cloud setup, never normal
desktop use. Actual Qt/Monaco/worker/crop/OpenCV flows pass through visible controls.
Window checks cover 1440×900, 1100×760 and 1024×700; the journey separately passed
at 125% scaling. Existing H.264/PyAV/local-socket and multi-worker tests remain.
Compileall, Linux launcher/capabilities and whitespace checks pass.

Actual local ADB binary/version/server/discovery worked and returned **no phone**;
query/screenshot/video remained NOT VERIFIED. The committed cloud report records
that result. Fixture transport/screens never count as physical Android evidence.

## GUI evidence

Actual Qt screenshots, visibly labeled fixture phones and synthetic screens:

![Script Studio](https://raw.githubusercontent.com/MD7-1337/Bot_Frm/fix/alpha-device-connect-and-ux-overhaul/docs/screenshots/alpha/alpha-studio.png)
![Device Manager](https://raw.githubusercontent.com/MD7-1337/Bot_Frm/fix/alpha-device-connect-and-ux-overhaul/docs/screenshots/alpha/alpha-devices.png)
![Visual Tools](https://raw.githubusercontent.com/MD7-1337/Bot_Frm/fix/alpha-device-connect-and-ux-overhaul/docs/screenshots/alpha/alpha-visual.png)
![Recorder](https://raw.githubusercontent.com/MD7-1337/Bot_Frm/fix/alpha-device-connect-and-ux-overhaul/docs/screenshots/alpha/alpha-recorder.png)

The full report links diagnostics, phone preview, settings, monitoring and compact screenshots.

## Windows, hardware and remaining milestones

Windows 10/11 x64 remains the target; **no Windows runtime/driver/installer test
was executed here**. Windows CI is configured, not a witnessed pass. Linux
headless DPI checks do not establish physical Windows monitor behavior.

No Android hardware was accessible. Collect the user's redacted report to identify
the PC restriction, involve IT for USB policy if needed, then validate actual
USB/Wi-Fi authorization, streaming, rotation, input, real target matching,
record/replay timing and two phones independently. ADB can itself restart a
version-mismatched server, so choose matching SDK tools deliberately.

OCR/UI hierarchy, full debugger, scheduling/recovery, richer telemetry, recorder
image conversion/curved multitouch and Windows packaging remain future milestones.
Recorder timing is approximate; coordinates are not automatically rescaled;
trusted Python has host-user permissions; already sent input cannot be reversed.

**Request user review before merging. Do not merge, delete branches, force-push
or alter main/branch protection as part of this draft.**
