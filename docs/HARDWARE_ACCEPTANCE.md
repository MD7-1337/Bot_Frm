# Windows and Android acceptance — NOT VERIFIED

Run these checks on a computer and phones you are authorized to use. The cloud
has no access to the user's school computer or phone; simulator passes do not
satisfy this checklist. Do not bypass school administrator policies.

Record Windows build, CPU/RAM, display DPI, phone model/Android version, tool
versions and USB/Wi-Fi mode. Avoid publishing device serials, screenshots or
pairing codes. Use **Settings → Check dependency health** and **Device Manager →
Diagnose Connection**; Copy Report redacts serial/home details by default.

- [ ] Launch using the documented Windows Python 3.12 environment; Monaco is ready
  without internet. Repeat using the generated portable on clean Windows without
  Python/Node. Save `--health-report report.json` from a windowed frozen build.
- [ ] Connect phone 1 by USB; authorize on its screen; verify exact ADB identity.
  Empty discovery is investigated as a host/driver/cable/permission issue.
- [ ] Pair and connect Android wireless debugging using its separate ports. Verify
  usable authorized identity; pairing code is absent from saved logs.
- [ ] Start scrcpy; verify decoded live frames. Rotate and change resolution;
  tap known landmarks, test letterboxes, double tap, hold, swipe, Back and Home.
- [ ] Capture a full-resolution region, save a target, insert in Monaco, run an
  approved visual click and verify the actual Android screen changes.
- [ ] Test image thresholds/scales/regions and optional OCR on real frames.
- [ ] Record controls, pause/resume/stop, reorder/edit/save/reopen, convert a tap
  to image target, replay through the trusted worker. External touches are not
  expected to be recorded.
- [ ] Break at a Monaco gutter line, inspect variables/stack, step into/over/out,
  continue, stop while paused and return to editing. Later edits remain intact.
- [ ] Schedule a bounded approved workflow; inspect history; close/restart before
  and during a run. Reapproval is required; uncertain input is not replayed.
- [ ] Disconnect during input/wait/debug/scheduled work. Old work must stay revoked
  after reconnect; only explicitly approved new work can start.
- [ ] Connect phone 2; run distinct scripts. Debugging/failure on one phone must
  not stop the other or route commands across devices.
- [ ] Emergency-stop running and paused workers and queued tasks; new runs remain
  blocked until reset and scheduled sources require fresh approval.
- [ ] Export/restore a project, reopen saved files and imported disabled tasks,
  verify screenshots/assets and migration backups; verify dirty-buffer warnings.
- [ ] Measure startup, responsiveness, memory/CPU, preview FPS/drops and recognition
  latency during a sustained one/two-phone workload and repeated close/reopen.
- [ ] Build/run portable and optional installer; verify per-user install, upgrade,
  uninstall and project preservation. Complete notices/license/signing review.

Report actual failures and steps in a local issue. Do not mark Beta accepted
until Windows, hardware, usability and packaging evidence has been reviewed.
