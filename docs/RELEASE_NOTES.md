# 0.2.0 Alpha development increment — 2026-10-31

This is source development on `feat/alpha-completion`, based on Phase 6 commit
`0a3e65cb8b84c23ded1cff7c6a202183357087b9`. No mainline merge, Windows binary
release or Beta designation is implied.

Added verified offline Monaco startup and dependency-health repair guidance;
worker-local Python line debugging; bounded read-only recovery and persistent
failure evidence; durable approved task scheduling; managed project preservation,
search and guarded archives; recorder timestamps; Windows packaging/CI recipes
and actual Linux simulator performance/source-smoke evidence.

Preserved the existing scripting API, isolated per-device workers, simulator/ADB
separation, OpenCV/OCR, recorder, scrcpy transport, trust dialogs and emergency stop.
New trust checks reject connection changes while approval dialogs are open.
Debugger variable contents stay in the inspector instead of general logs.

See [ALPHA_COMPLETION.md](ALPHA_COMPLETION.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md)
and [HARDWARE_ACCEPTANCE.md](HARDWARE_ACCEPTANCE.md) before acceptance testing.
