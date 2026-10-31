# Managed automation projects

The **Projects** workspace manages a versioned `project.json` and ordinary local
files. Project operations never execute Python, connect devices or authorize
scheduler tasks. Existing script tabs, the image library and project explorer
remain available in Script Studio.

Choose **New project**, select its parent directory and enter a new folder name.
The application creates `scripts`, `images`, `recordings`, `tasks`, `settings` and
`run_configurations`. Save scripts and recorder sessions into these directories
using their existing Save controls. Capture image targets into `images`.

**Open project** validates the manifest. The Phase 6 schema-1 manifest is migrated
to schema 2 only during this explicit open operation. Before replacement, the
exact original bytes are preserved in `.project-v1-<unique-id>.json` beside the
manifest. If validation, backup or the atomic replacement fails, the original
manifest stays intact. Unknown newer schema versions are rejected. Selecting an
ordinary image-library folder in Script Studio does not create or migrate a
manifest.

**Rename** changes the project's display name, without moving its directory or
breaking script/image references. **Save metadata** preserves the current validated
metadata atomically. Another application's changes to the manifest produce a
conflict error; reopen the project before writing again. Script files retain their
existing atomic-save and unsaved-change prompts.

## Preservation and sharing

**Export ZIP** and **Create backup** create identical portable preservation
archives with a new filename. Save edited script tabs and recorder sessions
before exporting: archives contain files saved on disk. Neither action replaces
an existing archive. Save archives outside the source project.

The archive includes the manifest, content under the six managed directories,
and root-level Python, Markdown and text files. Hidden paths, known credential
filenames, key/certificate files, logs and Python bytecode are excluded. Arbitrary
folders, virtual environments, repository data and local caches are excluded.
These rules cannot detect secrets embedded in Python or other allowed content;
review scripts and settings before sharing an archive.

**Import / restore ZIP** always extracts into a **new directory**. It validates
all names and sizes before extraction, extracts into temporary staging, validates
the project and promotes the completed directory. A corrupt archive leaves no
partially imported destination. Existing projects are never overwritten or
deleted. Restore a backup beside the existing project, compare the two, then
choose which copy to open.

**Duplicate** copies saved project content into a new directory and assigns a new
project identifier. Recent projects are stored in the user's application settings.
Opening a missing recent path reports an error and leaves other projects intact.

Portable path checks reject traversal, absolute/drive paths, symlinks, special
files, case-colliding names, Windows reserved names and malformed ZIP entries.
Limits are 2,000 entries, 32 MiB per file, 256 MiB uncompressed project content and
1 MB metadata. Exports use the same limits. ZIP CRC validation detects corrupted
members; archives are not authenticated or signed. Filesystem checks are a normal
local-use boundary, not protection against an attacker changing parent directories
concurrently.

## Finding content

Project search scans saved UTF-8 Python, JSON, Markdown and text files, with a
1 MB limit per searchable file and up to 200 displayed matches. Double-click a
Python result to open the source. **Check image references** parses Python without
executing it and reports missing or unsafe literal image filenames, using the
same contained image resolution as the runtime. Dynamically computed paths are
not evaluated. Syntax-invalid and non-UTF-8 scripts are skipped by this check.

## Autosave and recovery copies

**Projects → Recovery & safety → Autosave recovery settings** controls recovery
copies for dirty saved scripts and untitled tabs. It is enabled by default with a
30-second interval, configurable from 5 to 600 seconds. Copies save under the
user data directory's `draft-recovery` folder, outside the project archive.
The timer never overwrites an original Python file. Use ordinary Save to update
that file, and save dirty tabs before exporting a project.

After process loss, a nonblocking notice directs you to **Recover unsaved
scripts**. Select copies and choose **Restore selected as unsaved tabs**. They
open as new unsaved buffers, preserving current files and existing edits. No
script runs and no device or scheduler approval is granted. If the original
project folder is unavailable, restore/move the project first; its recovery
copies remain intact. Recovery covers the last completed autosave, so edits
newer than the configured interval may be missing.

A normal clean close retains ordinary Save/Discard/Cancel prompts and removes
only that process's own recovery journal. Previous crashed-session copies stay
available until the user explicitly deletes them in the recovery dialog.
**Delete selected recovery copies** confirms permanent removal of only those
copies; saved scripts and open tabs stay intact. It refuses a snapshot that
changed after inspection. Copies can contain private source: review them before
sharing, and keep the user data directory protected. Invalid journals remain
preserved and show a readable problem instead of being overwritten.

Recovery is bounded to 20 buffers per session, 1 MB UTF-8 per source/saved
baseline, 42 MB per encoded journal and 100 MB across journals. Atomic replacement
keeps the last completed copy if writing fails. Storage exhaustion produces an
error and does not automatically delete older user recovery data.

## Recognition and run configuration editor

**Configure project** has native controls for similarity threshold, explicit
scales, preprocessing and an optional original-screen region. **Insert
recognition preset** validates an existing contained image target and inserts
ordinary editable `Pattern(...)` Python using these values. It does not silently
change the scripting API's default behavior or execute recognition/input.

The Run scripts tab edits named project-relative Python script presets. Add a
script from inside the project, rename the preset or remove its row. **Open run
preset** opens the selected saved script in Script Studio. Select the device and
approve normal Run or Debug separately. Presets do not store device trust or
silently launch code. Invalid scales, regions, duplicate preset names and paths
outside the project are rejected before metadata is written.

## Project trash and damaged metadata

**Recovery & safety → Move project to trash** requires typing the exact project
display name. It refuses unsaved tabs, active/pending workers, enabled project
tasks, recording or background operations. The complete directory, including
files deliberately omitted from portable exports, moves into a sibling
`.studio-trash/<original-name>-<unique-id>` folder. Nothing is permanently
deleted. Clean open tabs are rebased to the preserved directory, so a later Save
cannot recreate files at the old location. Open that directory or move it back
to restore the project. Previously assigned disabled tasks require explicit path
review/reassignment; no execution is resumed.

**Recover project metadata** selects a damaged project's directory and a regular
JSON metadata backup, validates it, and asks before restoring. The exact current
`project.json` bytes are preserved in `.project-before-recovery-<id>.json` before
atomic replacement. A valid schema-1 migration backup is converted to schema 2;
unknown versions or invalid backups leave the current file untouched. This
recovers metadata only, not missing script/image file contents; use an archive
restore for complete project recovery.

## Portable task and workflow definitions

Save metadata, Export ZIP and Create backup snapshot the current project's local
task definitions into the manifest. Definitions contain source and portable
relative script paths and ordered workflow definitions; execution approval and live device connections are not
exported. After opening a restored project, **Import project task definitions**
explicitly copies these records into Task Manager with new identifiers and
remapped dependencies. Tasks/workflows import together transactionally with new
identities, disabled and unapproved. Review each
script and device before enabling it or approving execution. Repeating this
import creates another set of definitions.

Backup retention policies, an external Git UI and automatic overwriting of saved
scripts are not implemented. Existing unsaved-tab warnings apply. Recovery
copies preserve buffers rather than serializing Python worker state; a crashed
run still needs state inspection and new approval. Use explicit script saves and
project archives for durable, portable preservation.

`tests/test_project_management.py` exercises real files and ZIPs, atomic-save
interruption, migration backup and failure, conflict detection, inert import,
portable malicious paths, symlink guards, bounded extraction and preservation.
Windows filesystem/runtime acceptance remains a separate gate.

`tests/test_draft_recovery.py` exercises atomic journal interruption, invalid and
symlink snapshots, explicit discard conflict detection, recognition/run presets,
metadata recovery and reversible project trash. The opt-in actual Qt/Monaco
probe deliberately terminates a process after autosave, restarts the application,
uses the native recovery dialog, verifies that source files were not overwritten
and no Python ran, and edits recovery/project settings through native widgets.
