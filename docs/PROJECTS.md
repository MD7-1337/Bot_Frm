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

## Current limits

Save metadata, Export ZIP and Create backup snapshot the current project's local
task definitions into the manifest. Definitions contain source and portable
relative script paths; execution approval and live device connections are not
exported. After opening a restored project, **Import project task definitions**
explicitly copies these records into Task Manager with new identifiers and
remapped dependencies. Imported tasks start disabled and unapproved. Review each
script and device before enabling it or approving execution. Repeating this
import creates another set of definitions.

Project metadata can preserve recognition settings and run configurations. The
project UI currently edits its display name. Advanced configuration
editing, a project deletion command, automatic script autosave, backup retention
and an external Git UI are not implemented. Existing unsaved-tab warnings apply.
There is no automatic recovery of an unsaved editor buffer after process loss.
Use frequent explicit script saves and project backups.

`tests/test_project_management.py` exercises real files and ZIPs, atomic-save
interruption, migration backup and failure, conflict detection, inert import,
portable malicious paths, symlink guards, bounded extraction and preservation.
Windows filesystem/runtime acceptance remains a separate gate.
