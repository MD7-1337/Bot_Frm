Completes configurable unsaved-buffer recovery, project presets and reversible
trash, exact-device groups and occurrence-correlated sequential workflows,
imported-source debugging with persistent breakpoints, and a native connection
wizard with redacted diagnostic export. Monaco source notifications now carry
document identity and revision so rapid tab changes preserve pending edits.

Adds native Windows and Ubuntu portable builders, a cross-platform CI workflow,
installer build/install/uninstall checks and an extracted frozen simulator journey
covering Monaco, debugger, recorder, scheduler/history and project restore.

Validation: pristine baseline 863 passed; expanded Linux source suite 926 passed,
0 failed, 0 skipped, including 30 real GUI cases. An actual 306 MiB Ubuntu
22.04/glibc2.35 portable passed relocated extraction, clean no-system-Python and
unprivileged-user smoke tests. Commit, checksums and evidence are recorded in
docs/RELEASE_VALIDATION.md. Windows CI/binaries and physical Android remain
unverified; this is 0.2.0 Alpha development, not a stable release.

Keep this PR draft and unmerged, targeting feat/alpha-completion. No mainline or
existing development branch changes, force pushes or automatic stable releases.
