# Debugging trusted scripts

The Debugger workspace runs the approved source snapshot in the existing isolated
per-device Python worker. Click Monaco's glyph gutter to toggle a line breakpoint,
select a device (including an explicitly labeled simulated phone), and choose
**Debug trusted script…** / F9. Approve the exact source and target through the
normal native trust dialog. An ordinary Run does not activate the debugger.

At a breakpoint, Variables shows bounded local and global previews, Call stack
shows the current project's frames, and the toolbar provides Continue, Pause,
Step over, Step into, Step out and Stop. Select another stack frame to inspect
its variables; double-click it to request source navigation. The device/run
selector keeps debug sessions independent. Output and exceptions remain visible
in both the debugger and the existing execution output. Breakpoints can be
disabled/re-enabled using the checked list. Active breakpoint updates apply only
when the editor still matches that run's approved source snapshot.

The current execution line decorates the source without changing the Python.
Edits during execution do not change the worker's compiled source; navigation is
refused when it would point at a changed buffer. Imported project modules can be
stepped through and inspected, but editable snapshot navigation and breakpoint
configuration currently target the main script only. Debugging library internals,
conditional/log/function breakpoints, watch expressions and arbitrary evaluation
in a console are not implemented. Compute values in the trusted script instead.
Stepping out stops at bdb's function return boundary. Native calls can delay pause
until the next Python/project or automation safe point.

## Architecture and security boundary

The implementation uses Python's established `bdb.Bdb` stepping and breakpoint
machinery, composed with the existing source-reporting/cancellation trace. Each
worker owns its debugger, frames, globals and device lease. GUI commands cross a
private inherited OS pipe as validated JSON. No debug TCP port is opened, and no
external connection or arbitrary evaluation request is accepted. Only one
bounded command may await acknowledgment, so command queues cannot grow while a
native call is blocked. GUI calls go through the asynchronous RuntimeService.

`debugpy`/DAP was considered. For this source increment, bdb provides the required
Python line/stack/step behavior without introducing an adapter subprocess, public
socket lifecycle, debugpy's separate tracing ownership or another heavyweight
bundled dependency. The small private transport is app-specific; it is not a DAP
implementation and does not provide interoperability with external IDE clients.
A future DAP adapter can reuse the GUI session model after its worker/spawn and
packaging behavior is validated.

Inspection deliberately does not call user-defined `__repr__`, properties or
evaluation hooks. Only exact builtin primitives/containers are rendered, with
bounded recursion, string/container counts and an encoded JSON size budget.
Other values display their type. Up to 20 project stack frames and 40 user
variables per scope are shown; unchanged injected API bindings are omitted.
This keeps inspection responsive and prevents misleading side effects from a
hostile representation method. It is not a sandbox: **trusted Python still has
the current OS user's file, process and network permissions**. Imported code and
script-created subprocesses remain within that same trust boundary.

Stop, emergency stop, disconnect invalidation and application shutdown retain
the coordinator's existing cancellation and bounded forced termination behavior.
A stopped debugger checks cancellation every 20 ms. Pausing one device does not
block another worker or the Qt event loop. An Android action already dispatched
cannot be undone, and a reconnect never resumes an obsolete session.

## Validation

`tests/test_debugger.py` uses actual spawned workers to verify a breakpoint,
source hash, locals/globals, step into/over/out, continue, stack-frame inspection,
stdlib imports, handled exceptions, pause without initial breakpoints, dynamic
breakpoints, bounded Unicode values, no user `__repr__` calls, cancellation while
stopped and a second device progressing independently. GUI acceptance also needs
the current integrated workbench probe; backend tests alone do not establish
Monaco-to-device GUI acceptance. Windows and physical-phone debugging remain
NOT VERIFIED until exercised on those platforms.

Failure classification/source navigation from the preceding phase remains
available in Activity & Logs. Recovery policies are documented separately in
`RECOVERY.md`; debug controls never automatically replay a failed Android input.
