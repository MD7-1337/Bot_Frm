Adds usable debugger, scheduler and project-preservation workflows to the Phase 6
desktop application, while repairing offline Monaco startup and dependency health.

Monaco gutter breakpoints now control the existing isolated device workers through
private JSON pipes and stdlib bdb. Native Tasks and Projects workspaces persist
approved schedules/history and guarded project archives. Recovery retries only
explicit read operations; reconnect/reset and emergency stop revoke task approval.
Failure history, optional fresh post-failure evidence and recorder timestamps are
preserved. Existing simulation, recognition, OCR, ADB/scrcpy and emergency-stop
architecture remains in place.

Validation includes the verified 687-test Phase 6 baseline, the expanded regression
suite in `docs/validation/alpha-tests.json`, actual Qt/Monaco/capture/debug/record/
schedule/export/restart acceptance and one/two/four independent simulated-worker
measurements. Screenshots and exact limitations are in `docs/ALPHA_COMPLETION.md`.

Windows packaging/CI and installer recipes are provided, but no Windows binary,
installer, remote CI pass or physical-phone acceptance is claimed. This remains
0.2.0 Alpha development with incomplete scope explicitly documented. Keep this
PR in draft and unmerged; its base is `feat/phase6-recognition-simulator`.
