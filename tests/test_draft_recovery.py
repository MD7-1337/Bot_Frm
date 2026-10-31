from pathlib import Path
import json
from uuid import uuid4

import pytest

from app.projects.drafts import DraftStore
from app.projects import management
from app.projects.management import ProjectError, ProjectStore


def document(root, **changes):
    return {"key": uuid4().hex, "path": str(root / "main.py"), "project": str(root),
            "source": "raise RuntimeError('never execute recovery data')", "saved": "original", **changes}


def test_draft_reopen_preserves_unsaved_and_untitled_without_touching_source(tmp_path):
    path = tmp_path / "main.py"
    path.write_text("original")
    identity = uuid4().hex
    values = [document(tmp_path), document(tmp_path, path=None, source="untitled", saved="")]
    DraftStore(tmp_path / "recovery").write(identity, values)
    restored = DraftStore(tmp_path / "recovery").read(identity)
    assert restored["documents"] == values
    assert path.read_text() == "original"
    assert DraftStore(tmp_path / "recovery").sessions()[0] == [restored]


def test_interrupted_autosave_keeps_last_complete_snapshot(tmp_path, monkeypatch):
    store = DraftStore(tmp_path / "recovery")
    identity = uuid4().hex
    store.write(identity, [document(tmp_path)])
    original = store.read(identity)
    def fail(source, destination):
        raise OSError("simulated atomic replace interruption")
    monkeypatch.setattr(management.os, "replace", fail)
    with pytest.raises(OSError):
        store.write(identity, [document(tmp_path, source="newer")])
    assert store.read(identity) == original
    assert not list(store.root.glob(".studio-save-*"))


def test_clean_close_removes_only_own_session_and_corrupt_records_are_preserved(tmp_path):
    store = DraftStore(tmp_path)
    one, two = uuid4().hex, uuid4().hex
    store.write(one, [document(tmp_path)])
    store.write(two, [document(tmp_path)])
    corrupt = tmp_path / (uuid4().hex + ".json")
    corrupt.write_bytes(b"broken JSON")
    store.remove(one)
    sessions, problems = store.sessions()
    assert [entry["session"] for entry in sessions] == [two]
    assert problems and corrupt.read_bytes() == b"broken JSON"


def test_explicit_draft_discard_preserves_other_buffers_and_refuses_changed_snapshot(tmp_path):
    store = DraftStore(tmp_path)
    identity = uuid4().hex
    one, two = document(tmp_path), document(tmp_path, path=None)
    store.write(identity, [one, two])
    old = store.read(identity)
    store.write(identity, [one, two])
    with pytest.raises(ValueError, match="changed"):
        store.discard_documents(identity, [one["key"]], expected_updated_at=old["updated_at"])
    current = store.read(identity)
    store.discard_documents(identity, [one["key"]], expected_updated_at=current["updated_at"])
    assert store.read(identity)["documents"] == [two]


@pytest.mark.parametrize("changes", [{"project": "relative"}, {"path": "../secret.py"}, {"source": 1}, {"saved": None}, {"key": "../escape"}])
def test_invalid_drafts_never_replace_existing_snapshot(tmp_path, changes):
    store = DraftStore(tmp_path)
    identity = uuid4().hex
    store.write(identity, [document(tmp_path)])
    before = store.read(identity)
    with pytest.raises(ValueError):
        store.write(identity, [document(tmp_path, **changes)])
    assert store.read(identity) == before


def test_symlink_draft_cannot_replace_external_file(tmp_path):
    store = DraftStore(tmp_path / "recovery")
    identity = uuid4().hex
    outside = tmp_path / "outside"
    outside.write_text("keep")
    try:
        (store.root / (identity + ".json")).symlink_to(outside)
    except OSError:
        pytest.skip("Host does not permit symlinks")
    with pytest.raises(ValueError):
        store.write(identity, [document(tmp_path)])
    assert outside.read_text() == "keep"


def test_configuration_drives_actual_script_path_and_editable_pattern(tmp_path):
    import cv2
    import numpy as np
    project = ProjectStore.create(tmp_path / "project", "Managed")
    script = project.root / "scripts/main.py"
    script.write_text("print('trusted only after approval')")
    cv2.imwrite(str(project.root / "images/target.png"), np.random.default_rng(0).integers(0, 255, (10, 10, 3), dtype=np.uint8))
    recognition = {"threshold": .95, "scales": [.8, 1.0], "preprocessing": "grayscale", "region": [1, 2, 30, 40]}
    project.configure(recognition, [{"name": "Morning", "script": "scripts/main.py"}])
    reopened = ProjectStore.open(project.root)
    assert reopened.configured_script("Morning") == script
    code = reopened.recognition_code("target.png")
    compile(code, "preset", "exec")
    assert '.similar(0.95)' in code and '.inRegion(Region(1, 2, 30, 40))' in code
    assert reopened.metadata["recognition"] == recognition


@pytest.mark.parametrize("recognition,runs", [
    ({"threshold": float("nan")}, []), ({"threshold": True}, []),
    ({"scales": []}, []), ({"scales": [10]}, []), ({"preprocessing": "execute"}, []),
    ({"region": [0, 1, 0, 4]}, []), ({}, [{"name": "Escape", "script": "../escape.py"}]),
    ({}, [{"name": "x", "script": "main.py"}, {"name": "X", "script": "other.py"}]),
])
def test_bad_configuration_is_rejected_before_manifest_write(tmp_path, recognition, runs):
    project = ProjectStore.create(tmp_path / "project", "Managed")
    before = (project.root / "project.json").read_bytes()
    with pytest.raises(ProjectError):
        project.configure(recognition, runs)
    assert (project.root / "project.json").read_bytes() == before


def test_project_trash_is_confirmed_reversible_and_preserves_unlisted_private_files(tmp_path):
    project = ProjectStore.create(tmp_path / "project", "Managed")
    private = project.root / ".env"
    private.write_text("private local data")
    with pytest.raises(ProjectError):
        project.trash("wrong")
    assert private.exists()
    destination = project.trash("Managed")
    assert not project.root.exists()
    assert (destination / ".env").read_text() == "private local data"
    assert ProjectStore.open(destination).metadata["name"] == "Managed"
    destination.rename(tmp_path / "restored")
    assert (tmp_path / "restored/.env").read_text() == "private local data"


def test_corrupt_manifest_recovery_preserves_original_bytes(tmp_path):
    project = ProjectStore.create(tmp_path / "project", "Managed")
    backup = tmp_path / "metadata.json"
    backup.write_bytes((project.root / "project.json").read_bytes())
    (project.root / "project.json").write_bytes(b"corrupt source bytes")
    restored = ProjectStore.recover_manifest(project.root, backup)
    assert restored.metadata["name"] == "Managed"
    copies = list(project.root.glob(".project-before-recovery-*.json"))
    assert len(copies) == 1 and copies[0].read_bytes() == b"corrupt source bytes"


def test_invalid_manifest_backup_never_replaces_current_corruption(tmp_path):
    project = ProjectStore.create(tmp_path / "project", "Managed")
    backup = tmp_path / "metadata.json"
    backup.write_text('{"schema_version":999}')
    (project.root / "project.json").write_bytes(b"preserve these bytes")
    with pytest.raises(ProjectError):
        ProjectStore.recover_manifest(project.root, backup)
    assert (project.root / "project.json").read_bytes() == b"preserve these bytes"
