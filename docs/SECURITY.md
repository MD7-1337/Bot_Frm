# Execution and data security boundaries

Automation scripts are ordinary trusted Python with the current user's operating
system permissions. A spawned worker protects GUI responsiveness and device/run
state; it is **not a sandbox**. Python can access files, import subprocess, start
descendants or use another ADB client. Run only source you trust. Built-in device
leases coordinate this application's actions, not other programs or hostile code.

The native host approves exact source snapshots and selected devices before
execution. Opening a project, importing an archive or loading recorder data must
not execute Python. Review generated code before trusting it. Scheduler approvals
must apply to the saved source digest, not a path whose content can change. Paused
or disconnected sessions do not grant approval for a later replacement device.

Local Monaco has a restricted QWebChannel for document metadata/text and image
previews. It cannot choose arbitrary host paths, approve script execution or send
phone commands. WebEngine requests/navigation remain constrained to local editor
resources; ordinary desktop startup must retain Chromium's sandbox. Headless test
overrides are specific to isolated CI and do not belong in launcher scripts.

ADB operations validate an explicit identity and use argument arrays with
`shell=False`. Android remote-shell arguments remain constrained by each API.
Simulation identities use a separate transport and explicit session capabilities;
they cannot fall through to ADB. Protect local project/configuration directories
with the same OS account boundary as other trusted applications.

Emergency stop revokes further built-in dispatch and cancels owned workers.
An already-sent tap cannot be undone. Transport failure can leave a command's
outcome uncertain; recovery must not silently replay unsafe input. Arbitrary
script-created subprocesses are not guaranteed to be contained by worker stop.

Imported archives require path containment, size/count bounds and symlink checks;
project exports must exclude credentials and machine-local approvals. Backup and
migration recovery should preserve original files. SQLite is local persistence,
not an authorization boundary against another process running as the same user.

Connection reports should redact serial/home data for sharing, and pairing codes
must never be persisted in logs. Screenshots, traceback text, project paths, task
source and debugger variable values can contain sensitive application data; keep
evidence private unless reviewed. No telemetry or automatic cloud upload is added.

Packaging uses pinned dependencies and a full Monaco hash manifest. Server
digests detect known-resource corruption; user-selected executable paths execute
with user permissions and must be trusted. No updater, public debugger endpoint,
signing claim or hostile-code isolation is implied by the source implementation.
Windows/physical-device acceptance and exact binary/license review remain release
gates; see the current validation report for observed results.
