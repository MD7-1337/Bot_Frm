# Phase 7 foundation: failure inspection

This increment adds a small real recovery foundation, not a breakpoint debugger.
Workers emit typed failure classifications, source path/line, bounded traceback
and actionable advice. Categories distinguish recognition, image asset, OCR
engine/dependency, device connection, unknown input outcome, geometry, unsupported
capabilities and ordinary Python failures. Advice uses exception classes rather
than guessing from arbitrary message text. Every event says `automatic_retry: false`.

In Activity & Logs, hover a failed run's Error for the classification/advice and
traceback. Double-click its row to navigate to the failing line in Monaco **when
the current document matches the executed source snapshot**. Different files or
later edits are preserved and produce an explanation instead of jumping to a
misleading line. Execution-line reporting excludes virtual PySide dependency
filenames; Python imports/functions and independent workers remain supported.

Pause/Resume remain cooperative worker execution controls. Existing tracing
reports current project execution without exposing locals or opening a debug
port. Emergency stop cancels paused and running workers; native calls can delay
cooperative stopping and owned workers retain bounded forced termination.

## Remaining debugger design

Implement DAP/debugpy as an explicit per-worker opt-in with a private local
endpoint, bounded lifecycle and source snapshots. Before exposing controls,
validate line breakpoints, continue/step over/into/out, stack/locals, representation
size limits, debug-console trust, shutdown while paused, independent devices and
emergency stop. Do not bind a remotely reachable debug server by default. No
breakpoint, stepping, stack/variable inspector or debug console is delivered now.

Recovery must be an explicit policy above failures, with bounded retries/backoff
only for operations whose safety is established. A transport timeout can mean an
input already happened. No action is automatically retried after reconnection.
Automatic failure screenshots, persistent execution history, policy editor and
explicit snapshot restart UI remain follow-up work. Recognition Inspector and
recorder evidence supply manual inspection now, without pretending to be an
automatic recovery system. Scheduling remains deferred.
