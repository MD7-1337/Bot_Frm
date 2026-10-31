# Persistent task scheduling

The Task Manager stores exact Python source snapshots, explicit device identities,
project roots, schedules, dependencies and execution decisions in a versioned
SQLite database under the application's user data directory. This is Alpha
functionality. Simulated-device tests do not establish Windows or phone support.

## Use the workspace

1. Choose an available phone or explicit Demo Mode session and edit your script.
2. Open **Task Manager → Create from editor…**. The task copies that exact editor
   snapshot and target. Choose a name, priority, timeout and schedule, then save.
3. Select the task and **Approve source…**. Review the complete source, target,
   project and SHA-256 fingerprint in the native dialog. Approval executes trusted
   Python with your OS permissions; worker isolation is not a security sandbox.
4. Choose **Run now**, or **Resume scheduling** to process due schedules. Run now
   enqueues a manual occurrence and resumes scheduling. Other already-approved due
   tasks can also dispatch when scheduling resumes.
5. Review persistent execution history below the task list and full output/errors
   in Activity & Logs. **Cancel task** cancels its pending executions and stops its
   owned worker. **Pause scheduling** stops new dispatches; running workers continue.
6. Edit metadata with **Edit…**. **Replace from editor…** assigns another exact
   source/device snapshot. Both revoke approval. Enable/disable changes eligibility;
   disabling a task does not undo an already-dispatched action. Delete confirms the
   loss of that task's history and preserves project files.

Every application start begins with scheduling paused and no approved sources.
Imported tasks are disabled and receive new identities. Disconnect, simulation
reset and emergency stop revoke affected approval. A fresh explicit approval is
required; obsolete work is never resumed after device reconnection.

## Schedules and workflow dependencies

- **manual**: only Run now creates an occurrence.
- **once**: enter an ISO timestamp with an offset, such as
  `2026-11-01T09:00:00+00:00`.
- **interval**: cadence in seconds, from one second to one year. The next decision
  advances from the prior intended occurrence rather than drifting from dispatch.
- **daily**: enter `HH:MM` and an IANA timezone, such as `Europe/Paris`.
- **weekly**: daily time plus comma-separated weekdays (`0` Monday through `6`
  Sunday). The intended timezone is persisted.

During the spring DST gap, nonexistent local times are skipped. During the fall
fold, the first occurrence is selected and the repeated wall time is not replayed.
The `tzdata` package is required on platforms without system IANA timezone data;
Windows setup must install it (see packaging documentation).

**Missed runs** supports `skip` or `run_once`. A five-second timer delivery window
allows ordinary event-loop jitter. Longer lateness follows that policy and
coalesces multiple elapsed intervals to one decision. Pausing for a long period
uses the same missed-run rule when resumed. Devices that are temporarily busy or
unavailable keep approved occurrences queued; a disconnect invalidation cancels
obsolete work and revokes approval.

Dependencies are task IDs, visible in the task table. A task is eligible when each
listed dependency's most recent execution completed successfully. Missing IDs,
self-dependencies and cycles are rejected. This supports simple sequential flows;
it does not offer a visual workflow editor or per-occurrence DAG correlation.
Higher priorities dispatch first, then earlier scheduled occurrences. Only one
task per serial is dispatched at a time, including workers started outside Task
Manager. The configured global worker cap is preserved. Four independent actual
spawned simulation workers are covered by the scheduler tests.

## Failure, cancellation and restart safety

Default retries are **zero**. A script can send an Android action before a later
recognition failure. Automatic whole-script restart therefore requires an explicit
`I confirm the ENTIRE script is safe to repeat` policy, renewed source approval,
and a limit of at most three retries. Backoff is bounded (1, 2, then 4 seconds).
Transport acknowledgment failures and device-disconnect errors revoke approval
and never automatically restart, even under that policy. Each attempt has a
positive, finite timeout of at most one day. Cancellation uses existing worker
cooperative stop and bounded forced termination; an already-sent Android action
cannot be undone.

A durable decision is recorded before dispatch; request acknowledgments map to
owned worker IDs. Unique task/occurrence keys prevent duplicate schedule decisions.
A crash after submission can leave an unknown external outcome. On next startup,
in-flight executions become **uncertain** and pending executions are cancelled.
They are never replayed automatically. An application close while a worker is
in flight can also leave its history uncertain if its final acknowledgment was
not persisted before shutdown. This does not promise exactly-once Android side
effects. One application owns its task database and device leases; coordinating
multiple separate application instances or external ADB clients is outside scope.

## Persistence and portable definitions

`TaskStore` uses schema version 1, parameterized SQL, transactional writes and
validated state updates. Unsupported schema versions are rejected while retaining
the file. Initial schema creation rolls back if a migration statement fails.
History is durable; active queues are bounded at 256 and task definitions at 1000.
The visible history shows the most recent 200 executions; it does not delete older
records. Simulated sessions/capability tokens and Python runtime state are never
stored in the task database.

`export_definitions(project_root)` returns portable JSON-safe task definitions.
Script paths must stay inside that project. Definitions carry source and target
identities, so review them before sharing. `import_definitions(definitions, root)`
remaps identities/dependencies and project paths, rejects traversal and symlink
escapes, validates the complete dependency graph, and inserts everything atomically.
Imports never grant trust, recreate a simulation, reconnect a device or run code.
Source snapshots do not freeze imported Python modules or image files on disk;
review your whole project before approving execution.

## Validation and remaining scope

Run the core scheduler tests with:

```bash
.venv/bin/python -m pytest -q tests/test_tasks.py
```

The opt-in native Qt journey creates a task through its visible controls, approves
its source, runs an actual simulation worker, verifies changed pixels/state and
reopens the SQLite history:

```bash
STUDIO_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -q tests/test_tasks_gui.py
```

Device-group expansion, a visual workflow builder, execution-history retention
configuration, cross-instance arbitration, calendar exceptions and per-occurrence
workflow dependency correlation remain follow-up work. Physical Android and
Windows runtime acceptance remain **NOT VERIFIED** until run on those platforms.
