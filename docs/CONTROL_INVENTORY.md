# Alpha functional control inventory

Date: 2026-10-30. Current shell: `fix/alpha-device-connect-and-ux-overhaul`.

Status vocabulary:

- **Working / verified** means exercised with real Qt/Monaco, actual Python
  workers/recognition, or the named adapter tests. It does not mean physical
  Android/Windows acceptance.
- **Hardware required** means the UI/adapter path is exercised with controlled
  fixtures, but the actual phone/USB/Wi-Fi result is NOT VERIFIED.
- **Partial** describes a deliberately bounded implemented capability.
- **Not implemented** is explicitly labeled and cannot create a fake task/run.

No unresolved broken control was observed in the final automated/visual pass.
This is not a claim that every Android device, application or Windows host works.

## Shell and files

| Controls | Prerequisites and actual route | Status / evidence |
| --- | --- | --- |
| Seven sidebar workspaces; Workspaces menu; Ctrl+1–7 | Switch the actual central page; shared preview/output widgets move to their workspace slots | Working / verified; native Qt journey and screenshots |
| Collapse sidebar; compact Preview toggle; View → Reset layout | Resize navigation, reveal/hide preview, reset real splitters; per-user preferences persist | Working / verified at 1440×900, 1100×760, 1024×700; 125% scaling journey |
| Header device selector | Select the matching DeviceInfo serial row; unavailable rows remain inspectable and cannot route input | Working / verified; serial safety suites |
| Commands button; Ctrl+Shift+P | Search existing QActions and invoke an enabled action; native Qt shortcut registered on the host window | Working / verified with focused keyboard activation; no execution bridge added |
| Emergency stop; Ctrl+Shift+F12; Reset emergency stop | Existing global runtime stop and manual-cancellation generation; reset only after acknowledgment | Working / verified by existing worker/UI safety suites; cannot reverse sent input |
| New/Ctrl+N, Open/Ctrl+O; script tabs/close buttons | Maintain up to 20 host-owned buffers; reopening a file selects its existing unsaved buffer | Working / verified, including unsaved tab switching |
| Save/Ctrl+S, Save as | Atomic source save; native dialog selects/approves a path; errors remain visible | Working / verified; preserved project/save-error test |
| File → Choose project; project Open… / Refresh / double-click files | Bounded background scan of Python/images; contained image roots; double-click opens scripts or targets | Working / verified in integrated fixture project; max 1000 files/directories |
| Insert API menu | Insert real supported Python calls; editor-not-ready state gives feedback | Working / verified by actual Monaco/API suites; ordinary editable Python |
| Help capabilities / connection troubleshooting | Show actual alpha limits or open the diagnostic workflow | Working; no debugger/OCR/scheduling success implied |

## Connections and previews

| Controls | Prerequisites and actual route | Status / evidence |
| --- | --- | --- |
| Automatic USB discovery / Refresh devices | Background `adb devices -l`, preserve current/multiple selections, update registry generations | Adapter and Qt verified; actual local ADB returns []; physical USB hardware required |
| Device cards and Details tab | Model/serial/state, observed screen metadata, Android version where accessible, assigned file and next action | Working / verified with unavailable states; no invented metadata |
| Save name/group; Select group | Save display labels in QSettings; select rows by saved group; serial routing unchanged | Working / verified in existing GUI regression |
| Connect | Validate explicit host:port, acknowledge transport, rediscover authorized serial and perform harmless query | Hardware required; real argv validation and visible unauthorized-connection fixture verified |
| Pair… | Separate pairing endpoint; password-style six-digit input; background `adb pair`; code absent from logs/history | Hardware required; native dialog wiring and adapter/redaction fixtures verified |
| Disconnect selected Wi-Fi | Exact endpoint only; invalidate queued controls/workers/frame before removing transport | Hardware required; visible fixture and failed-disconnect regression verified; USB disconnect is physical |
| Reconnect | TCP: explicit connect to selected endpoint. USB/unreadable serial: guidance and discovery refresh | Hardware required; no server kill, OS permission change or blind script replay |
| Diagnose Connection (header/tab); Include video; Cancel check | Eight explicit stages cover binary/path, version, server, raw discovery/state, query, screenshot and stream/frame; cancellation is bounded by current subprocess/native operation | Working / verified by unit/Qt fixtures and actual local no-phone ADB. Physical final stages NOT VERIFIED |
| Redact serials; Copy Diagnostic Report | Copy text only; default serial/home redaction, no pairing code or screenshot pixels | Working / verified; privacy default is configurable |
| ADB path & settings | Open the actual Devices & video settings | Working; host USB permissions still require IT/admin where applicable |
| Open preview | Start or reveal selected phone's managed stream, avoiding an unnecessary restart | Hardware required; visible button now demonstrably produces fixture frames |
| Start live; Stop; More → Start all connected | Existing StreamManager; independent capped video sessions; stop invalidates frames and cleans owned resources | Actual protocol/H.264/socket suites pass; physical scrcpy NOT VERIFIED |
| More → Screenshot fallback | Explicitly stop video, select actual ADB capture mode and poll when idle | Hardware required; never labeled live video |
| Quality; FPS/bitrate/max edge | Reveal real validated stream options, applied at next explicit start | UI/options verified; physical encoder behavior/latency NOT VERIFIED |
| Preview tap/double tap/hold/drag; Home/Back | Map preview to original pixels, reject letterboxes/stale frames, use exact serial and idle lease | Qt/adapter verified; actual phone/app recognition of input hardware required |
| Preview Capture; Capture PNG / target toolbar/menu | Background original-resolution capture, atomic user-chosen PNG or region dialog | Fixture Qt verified, including downscaled preview regression; physical capture hardware required |

## Visual Tools and capture

| Controls | Prerequisites and actual route | Status / evidence |
| --- | --- | --- |
| Choose project / Refresh library / select target | Bounded contained file scan, raster-only background decode, actual thumbnail | Working / verified; external changes need explicit Refresh |
| Capture region / Save full screenshot | Selected authorized phone; same real capture service as above | Hardware required; complete visible fixture journey verified |
| Minimum score, scales, offset, search bounds | Validate and build real immutable Pattern settings; pixels use original Android geometry | Working / verified; explicit scales, no automatic resolution independence |
| Insert click/find/wait/path | Require a target and ready Monaco; validate asset and insert ordinary Python | Working / verified with actual editor and preserved escaping/containment tests |
| Test on fresh phone screen | Capture new frame and run real OpenCV with configured settings; no tap sent | Actual recognition verified on fixture pixels; physical target matching hardware required |
| Capture dialog drag/crop/coordinates | Frozen image and inverse mapping; crop remains separate from fresh comparison | Working / verified with real Qt pointer events and image pixels |
| Save crop + insert reference | Native user-chosen path, atomic PNG, contained reference validation and Monaco insertion | Working / verified end to end |
| Test match / threshold / explicit scales / search only rectangle | Bounded background fresh capture and matching; show scores, regions and ambiguity | Working / verified; app timing/protected Android content unverified |
| Close capture dialog | Defer close during owned bounded operation, then release host/dialog references | Working / verified cleanup regressions |

## Script execution, recorder and settings

| Controls | Prerequisites and actual route | Status / evidence |
| --- | --- | --- |
| Run/F5 | Ready editor, selected idle phone, reset stop, valid source/project; host trust approval; spawned worker | Real Qt/Monaco/worker verified with explicit fixture backend; phone action hardware required |
| Pause/F6, Resume/Shift+F6, Stop/Shift+F5 | Selected active run; enable state follows acknowledged run state | Working / verified; pause is a safe point, not suspension of every native call |
| Run editor on selected phones/Ctrl+F5; Assign Python file; Run assigned files | Selected authorized idle devices and contained trusted snapshots; independent contexts/logs | Existing actual multi-worker Qt tests retained; two physical phones NOT VERIFIED |
| Script run rows / Output and events; Activity & Logs | Select run for controls, inspect output/error/tracebacks/observed line | Working / verified; current-line decoration is not a full debugger |
| Parent process CPU/RSS metrics | Best-effort standard-library platform adapter; unavailable stays unavailable | Linux observations verified; Windows code/CI added but runtime NOT VERIFIED. Child/worker totals are not included |
| Recorder Start / Pause-resume / Stop | One idle serial/generation; ticket-based completed studio controls only | Working / verified, including disconnect/emergency and stale ticket rejection |
| Timeline edit/delete/up/down; Add delay | Stop first; edit one Python call per row; validate before source/save/replay | Working / verified; conditions/loops belong in Monaco |
| Insert Python; Save session / Open session | Ordinary source or bounded versioned JSON; no execution on load; transactional validation | Working / verified; screenshots/physical touches not automatically recorded |
| Replay on selected phone | Review screen/coordinates, select current device, approve normal trusted worker execution | Actual spawned fixture replay verified; real-phone timing hardware required |
| Appearance theme/font / Apply | Apply consistent Qt palette/style and Monaco theme/font, save user preferences | Working / verified light/dark and actual Monaco font size |
| Choose ADB; ADB/server paths / Apply | Rebind only while runs, streams and jobs idle; explicit missing paths remain explicit errors; environment overrides documented | Working / verified live-operation guard and actual missing-binary GUI diagnostic |
| Video defaults / discovery interval / worker limit | Apply next-start encoder options and discovery interval; worker limit at next launch | Implemented validated controls; physical capacity limits unmeasured |
| Privacy default / Apply | Set diagnostic serial redaction default; no telemetry/upload action | Working / verified settings/report path |
| Task Manager assignment link | Open real Device Manager assignments; page explicitly says scheduler/recovery is not implemented | Scheduling **not implemented**; no fake scheduled task controls |

## Deliberate limits

Recognition now includes real template matching and RGB pixel/color Python APIs.
OCR/text recognition, UI hierarchy, full debugger, scheduling/recovery, automatic
recorder image conversion and Windows packaging are **not implemented in this
increment**. Do not infer them from the roadmap or Task Manager explanation.

The previous 569 tests did not cover the user's physical PC policy or a native
Windows/phone setup. Many older probes also called controller methods or sent
synthetic events without requiring visible widgets. The new alpha journey
requires visible, enabled control centers before clicking, exercises wrong-path
and permissions failures, uses actual Monaco and spawned workers, and checks
multiple sizes/scaling. Those tests strengthen software evidence; they still do
not turn simulated transport into real-device validation.
