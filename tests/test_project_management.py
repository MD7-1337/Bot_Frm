from __future__ import annotations

import json
from pathlib import Path
import stat
import zipfile

import pytest

from app.projects import management
from app.projects.management import MANIFEST, ProjectConflictError, ProjectError, ProjectStore


@pytest.fixture
def project(tmp_path):
    return ProjectStore.create(tmp_path / "project", "A project")


def archive(path, entries):
    with zipfile.ZipFile(path, "w") as output:
        for name, payload in entries:
            # Preserve attacker-supplied ZIP names: ZipInfo's constructor
            # rewrites backslashes on Windows before the reader can inspect them.
            if isinstance(name, str):
                info = zipfile.ZipInfo()
                info.filename = name
                name = info
            output.writestr(name, payload)
    return path


def test_create_open_rename_and_configuration_round_trip(project):
    original_id = project.metadata["id"]
    data = project.metadata
    data["recognition"] = {"threshold": .92}
    data["task_definitions"] = [{"name": "nightly", "enabled": False}]
    project.save(data)
    project.rename("Renamed")
    reopened = ProjectStore.open(project.root)
    assert reopened.metadata["id"] == original_id
    assert reopened.metadata["name"] == "Renamed"
    assert reopened.metadata["recognition"]["threshold"] == .92
    assert reopened.metadata["task_definitions"][0]["enabled"] is False
    assert all((project.root / folder).is_dir() for folder in management.DIRECTORIES)


def test_metadata_property_is_not_live_mutable_state(project):
    data = project.metadata
    data["name"] = "changed"
    assert project.metadata["name"] == "A project"


def test_creation_never_overwrites_existing_directory(project):
    (project.root / "keep.txt").write_text("user data")
    with pytest.raises(FileExistsError):
        ProjectStore.create(project.root, "Replacement")
    assert (project.root / "keep.txt").read_text() == "user data"


def test_save_detects_concurrent_manifest_change(project):
    another = ProjectStore.open(project.root)
    another.rename("External")
    with pytest.raises(ProjectConflictError):
        project.rename("Clobber")
    assert ProjectStore.open(project.root).metadata["name"] == "External"


def test_failed_atomic_save_preserves_original_and_cleans_staging(project, monkeypatch):
    original = (project.root / MANIFEST).read_bytes()
    def interrupted(*_args):
        raise OSError("injected interrupted replace")
    monkeypatch.setattr(management.os, "replace", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        project.rename("Lost")
    assert (project.root / MANIFEST).read_bytes() == original
    assert not list(project.root.glob(".studio-save-*"))
    assert project.metadata["name"] == "A project"


def test_schema_one_migration_retains_demo_flag_and_original_backup(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    original = b'{"schema_version":1,"simulation":true}\n'
    (root / MANIFEST).write_bytes(original)
    project = ProjectStore.open(root)
    assert project.metadata["simulation"] is True
    assert project.metadata["schema_version"] == 2
    assert [path.read_bytes() for path in root.glob(".project-v1-*.json")] == [original]


def test_migration_can_be_refused_without_changing_project(tmp_path):
    (tmp_path / MANIFEST).write_text('{"schema_version":1}')
    with pytest.raises(ProjectError, match="explicit migration"):
        ProjectStore.open(tmp_path, migrate=False)
    assert not list(tmp_path.glob(".project-v1-*.json"))


def test_failed_migration_preserves_original_and_backup(tmp_path, monkeypatch):
    original = b'{"schema_version":1}'
    (tmp_path / MANIFEST).write_bytes(original)
    def interrupted(*_args):
        raise OSError("interrupted migration")
    monkeypatch.setattr(management.os, "replace", interrupted)
    with pytest.raises(OSError):
        ProjectStore.open(tmp_path)
    assert (tmp_path / MANIFEST).read_bytes() == original
    assert [path.read_bytes() for path in tmp_path.glob(".project-v1-*.json")] == [original]


@pytest.mark.parametrize("payload", [b"not JSON", b"[]", b'{"schema_version":true}', b'{"schema_version":2,"name":NaN}', b'{"schema_version":1,"schema_version":2}', b'{"schema_version":999}'])
def test_corrupt_or_unsupported_metadata_is_not_rewritten(tmp_path, payload):
    (tmp_path / MANIFEST).write_bytes(payload)
    with pytest.raises(ProjectError):
        ProjectStore.open(tmp_path)
    assert (tmp_path / MANIFEST).read_bytes() == payload


def test_manifest_size_limit_is_enforced(tmp_path):
    (tmp_path / MANIFEST).write_bytes(b" " * (management.MAX_MANIFEST_BYTES + 1))
    with pytest.raises(ProjectError, match="exceeds"):
        ProjectStore.open(tmp_path)


def test_export_import_restore_saved_content_and_do_not_execute(project, tmp_path):
    marker = tmp_path / "MUST_NOT_EXIST"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    (project.root / "scripts" / "automation.py").write_text(source)
    (project.root / "images" / "target.png").write_bytes(b"fixture image")
    (project.root / "recordings" / "session.json").write_text('{"actions":[]}')
    exported = project.export(tmp_path / "project.zip")
    imported = ProjectStore.import_archive(exported, tmp_path / "imported")
    restored = ProjectStore.restore(exported, tmp_path / "restored")
    assert imported.metadata == restored.metadata == project.metadata
    assert (imported.root / "scripts" / "automation.py").read_text() == source
    assert (restored.root / "images" / "target.png").read_bytes() == b"fixture image"
    assert not marker.exists()


def test_export_excludes_caches_credentials_and_unrelated_files(project, tmp_path):
    for name in (".env", "credentials.json", "identity.key", "report.log"):
        (project.root / "scripts" / name).write_text("private")
    (project.root / "scripts" / "good.py").write_text("print('ok')")
    (project.root / "unrelated").mkdir()
    (project.root / "unrelated" / "document.txt").write_text("unrelated")
    path = project.export(tmp_path / "safe.zip")
    with zipfile.ZipFile(path) as output:
        assert sorted(output.namelist()) == [MANIFEST, "scripts/good.py"]


def test_export_never_replaces_existing_archive(project, tmp_path):
    target = tmp_path / "backup.zip"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        project.backup(target)
    assert target.read_bytes() == b"keep"


def test_export_cannot_write_into_own_project(project):
    with pytest.raises(ProjectError, match="outside"):
        project.export(project.root / "backup.zip")


def test_duplicate_gets_new_identity_and_preserves_content(project, tmp_path):
    (project.root / "scripts" / "main.py").write_text("x = 1\n")
    copied = project.duplicate(tmp_path / "copy")
    assert copied.metadata["id"] != project.metadata["id"]
    assert copied.metadata["name"] == "A project (copy)"
    assert (copied.root / "scripts" / "main.py").read_text() == "x = 1\n"
    assert not list(tmp_path.glob(".studio-duplicate-*"))


def test_failed_duplicate_metadata_write_leaves_no_partial_destination(project, tmp_path, monkeypatch):
    def failed(*_args):
        raise OSError("injected duplicate metadata failure")
    monkeypatch.setattr(ProjectStore, "save", failed)
    with pytest.raises(OSError, match="duplicate metadata"):
        project.duplicate(tmp_path / "copy")
    assert not (tmp_path / "copy").exists()
    assert not list(tmp_path.glob(".studio-duplicate-*"))
    assert ProjectStore.open(project.root).metadata["name"] == "A project"


@pytest.mark.parametrize("unsafe", ["../escape.py", "/absolute.py", "scripts/../../escape.py", "scripts\\escape.py", "scripts/C:ads.py", "scripts/CON.py", "scripts/trailing. ", "scripts//twice.py", "./scripts/odd.py", "C:/escape.py", "C:escape.py", "//server/share.py", "\\\\server\\share.py", "scripts/../escape.py", "scripts/escape.py\x00hidden"])
def test_archive_rejects_unsafe_portable_paths(project, tmp_path, unsafe):
    path = archive(tmp_path / "evil.zip", [(MANIFEST, (project.root / MANIFEST).read_bytes()), (unsafe, b"untrusted")])
    destination = tmp_path / "imported"
    with pytest.raises(ProjectError):
        ProjectStore.import_archive(path, destination)
    assert not destination.exists()
    assert not (tmp_path / "escape.py").exists()


def test_archive_rejects_duplicate_windows_case_paths(project, tmp_path):
    path = archive(tmp_path / "evil.zip", [(MANIFEST, (project.root / MANIFEST).read_bytes()), ("scripts/A.py", b"a"), ("scripts/a.py", b"b")])
    with pytest.raises(ProjectError, match="colliding"):
        ProjectStore.import_archive(path, tmp_path / "destination")


def test_archive_rejects_zip_symlink(project, tmp_path):
    info = zipfile.ZipInfo("scripts/link.py")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    path = archive(tmp_path / "link.zip", [(MANIFEST, (project.root / MANIFEST).read_bytes()), (info, b"/etc/passwd")])
    with pytest.raises(ProjectError, match="special"):
        ProjectStore.import_archive(path, tmp_path / "destination")


def test_archive_import_size_limit_and_no_partial_destination(project, tmp_path, monkeypatch):
    path = archive(tmp_path / "large.zip", [(MANIFEST, (project.root / MANIFEST).read_bytes()), ("scripts/main.py", b"x" * 1000)])
    monkeypatch.setattr(management, "MAX_PROJECT_BYTES", 600)
    with pytest.raises(ProjectError, match="size"):
        ProjectStore.import_archive(path, tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_archive_file_count_limit_before_extraction(project, tmp_path, monkeypatch):
    path = archive(tmp_path / "many.zip", [(MANIFEST, (project.root / MANIFEST).read_bytes()), ("scripts/a.py", b"a")])
    monkeypatch.setattr(management, "MAX_FILES", 1)
    with pytest.raises(ProjectError, match="many"):
        ProjectStore.import_archive(path, tmp_path / "destination")


def test_invalid_import_manifest_leaves_existing_files_and_new_destination_untouched(tmp_path):
    source = archive(tmp_path / "invalid.zip", [(MANIFEST, b"broken"), ("scripts/main.py", b"x")])
    (tmp_path / "keep.txt").write_text("keep")
    with pytest.raises(ProjectError):
        ProjectStore.import_archive(source, tmp_path / "destination")
    assert not (tmp_path / "destination").exists()
    assert (tmp_path / "keep.txt").read_text() == "keep"
    assert not list(tmp_path.glob(".studio-import-*"))


def test_restore_requires_new_directory(project, tmp_path):
    path = project.backup(tmp_path / "backup.zip")
    with pytest.raises(FileExistsError):
        ProjectStore.restore(path, project.root)


def test_export_rejects_symlinks_in_project_content(project, tmp_path):
    external = tmp_path / "outside.py"
    external.write_text("private")
    try:
        (project.root / "scripts" / "link.py").symlink_to(external)
    except OSError:
        pytest.skip("Host does not permit unprivileged symlink creation")
    with pytest.raises(ProjectError, match="regular"):
        project.export(tmp_path / "archive.zip")


def test_open_rejects_symlink_manifest(project, tmp_path):
    payload = (project.root / MANIFEST).read_bytes()
    target = tmp_path / "outside.json"
    target.write_bytes(payload)
    (project.root / MANIFEST).unlink()
    try:
        (project.root / MANIFEST).symlink_to(target)
    except OSError:
        pytest.skip("Host does not permit unprivileged symlink creation")
    with pytest.raises(ProjectError, match="regular"):
        ProjectStore.open(project.root)


def test_project_text_search_and_missing_assets_are_inert_and_bounded(project):
    (project.root / "scripts" / "main.py").write_text('click("missing.png")\nprint("needle")\nprint("NEEDLE")\n')
    results = project.search("needle", limit=1)
    assert len(results) == 1
    assert (results[0].path, results[0].line) == ("scripts/main.py", 2)
    assert project.missing_assets() == ["scripts/main.py:1: missing.png"]


def test_json_invalid_values_rejected_without_overwrite(project):
    before = (project.root / MANIFEST).read_bytes()
    data = project.metadata
    data["recognition"] = {"threshold": float("nan")}
    with pytest.raises(ProjectError, match="finite"):
        project.save(data)
    assert (project.root / MANIFEST).read_bytes() == before
