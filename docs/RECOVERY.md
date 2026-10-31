# Bounded recovery and persistent failure evidence

Recovery separates safe repeated observations from Android input. A lost tap
response does not prove that the tap failed. No recovery operation reconnects a
device, repeats input, restarts Python or resumes an obsolete run automatically.
The ordinary runtime continues to enforce leases, connection generations, pause,
cancellation and bounded forced worker termination.

## Explicit read recovery in scripts

Trusted scripts can opt into a small bounded retry policy:

```python
from app.automation.recovery import RecoveryEngine, RetryPolicy

observations = RecoveryEngine(
    device,
    RetryPolicy(max_attempts=3, initial_delay=0.2,
                multiplier=2, max_delay=1, budget=5),
)
target = observations.read("find", "images/start.png")
click(target)  # One explicit input after successful observation; never retried.
```

The default policy makes one attempt. Policies allow at most ten total attempts,
bounded exponential backoff and a finite total budget of at most 24 hours. The
read-only allowlist contains screenshot, resolution, pixel, color, image and OCR
observations plus their explicit wait methods. `click`, `tap`, `swipe`, application
launch/stop, key/text input, overloaded `wait` and arbitrary callbacks are refused.
This keeps image recognition followed by input outside the automatic retry loop.

Only typed `ImageNotFound`, `RecognitionTimeout` and `FrameUnavailable` failures
can retry. Missing/corrupt assets, ambiguous targets, missing OCR dependencies,
Python errors, transport timeouts, failed commands and disconnected/offline or
unauthorized devices propagate immediately. `exists` returning no match is a
successful observation, not a failed attempt.

Backoff uses the assigned Device's normal interruptible sleep. Pause and emergency
stop therefore retain their existing behavior. The monotonic budget includes
observations and backoff; image/text waits are clamped to the remaining budget.
An already-running native capture or OCR call retains its existing transport
timeout and cannot be unwound by the Python recovery deadline. Its result is
rejected if it returns after the total budget expires. This is not a hard native
execution deadline or a guarantee that every observation will succeed.

## Source-specific progress markers

Application hosts can supply `RecoverySession.for_source(serial,generation,source)`
and a `current_session` callback to `RecoveryEngine`. Every attempt and progress
marker validates the exact serial, generation and SHA-256 source snapshot.
`checkpoint(name,data)` creates a bounded immutable JSON marker;
`verify_checkpoint(marker)` refuses another source/device or an obsolete
connection. Marker data is limited to 16 KiB and must be finite JSON.

Checkpoints record progress only. They do not serialize a Python stack, grant a
device lease, reconnect or authorize script execution. The caller must explicitly
inspect state and start a newly approved run through the ordinary runtime when a
restart is appropriate. Checkpoint payloads are not automatically persisted.

## Local failure history

`RecoveryJournal` stores worker error events in versioned SQLite with atomic
transactions, validated data, event deduplication, bounded text and retention.
The default is 500 records; configurable retention is limited to 5,000. Retained
PNG evidence is limited to 20 MB across records. Reclaimable SQLite pages are
reused; removal does not immediately shrink the database file. Future schemas
are rejected without being overwritten. There is no network upload or telemetry.

The recovery history widget shows device/run identity, failure category,
traceback, source line and advice. **Capture a fresh screen after failures** is
off by default. If enabled by the host, evidence must come from the still-current
connection and is explicitly labeled as post-failure capture. The journal never
fetches a screen itself and never substitutes an old preview as fresh evidence.
Screen content can contain private data. Exported JSON diagnostics omit screen
pixels but include local device/path details; review them before sharing.

The worker's failure classification always reports `automatic_retry: false`.
That advice describes the failed script/action as a whole. A separate explicitly
configured read loop may make bounded observations before the error reaches the
worker boundary. Whole-script scheduler restart policies have separate explicit
authorization and should only be enabled when the complete script is safe to
repeat; read recovery never infers that property.

## Evidence and limits

Automated tests exercise actual Device reads, cancellation during backoff,
generation/source invalidation, finite policies, budget handling, immutable
markers, persistent reopen, duplicate events, schema rejection and rollback of
an interrupted retention transaction. A real spawned worker finds the delayed
reward target in the SQLite-backed simulator without sending input. A separate
Qt Widgets journey opens persisted failure evidence and reorders/deletes recorder
rows while checking timestamp and screenshot ownership.

These checks establish simulator and Linux behavior. Windows runtime, physical
phone failures, real transport uncertainty and USB reconnect acceptance remain
**NOT VERIFIED** until exercised on appropriate hardware.
