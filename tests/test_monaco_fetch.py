import base64
import hashlib
import io
from pathlib import Path
import tarfile

import pytest

from app.editor.assets import validate_monaco
from tools import fetch_monaco


def configure_archive(tmp_path, monkeypatch):
    content = b"verified AMD loader fixture"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        member = tarfile.TarInfo("package/min/vs/loader.js")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    data = stream.getvalue()
    monkeypatch.setattr(fetch_monaco, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_monaco, "INTEGRITY", base64.b64encode(hashlib.sha512(data).digest()).decode("ascii"))
    monkeypatch.setenv("STUDIO_DOWNLOAD_CACHE", str(tmp_path / "cache"))
    manifest = {"version": "fixture", "files": {"vs/loader.js": {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}}}
    monkeypatch.setattr(fetch_monaco, "validate_monaco", lambda root: validate_monaco(root, manifest=manifest))
    calls = []
    def download(*args, **kwargs):
        calls.append(True)
        return io.BytesIO(data)
    monkeypatch.setattr(fetch_monaco.urllib.request, "urlopen", download)
    return content, calls


def test_monaco_installs_verified_tree_and_reuses_offline(tmp_path, monkeypatch):
    content, calls = configure_archive(tmp_path, monkeypatch)
    fetch_monaco.main()
    assert (tmp_path / "editor_web/vendor/vs/loader.js").read_bytes() == content
    assert len(calls) == 1
    fetch_monaco.main()
    assert len(calls) == 1
    # A damaged local install is repaired from the independently verified cache.
    (tmp_path / "editor_web/vendor/vs/loader.js").write_bytes(b"corrupt")
    fetch_monaco.main()
    assert len(calls) == 1
    assert (tmp_path / "editor_web/vendor/vs/loader.js").read_bytes() == content


def test_monaco_replacement_failure_restores_previous_install(tmp_path, monkeypatch):
    configure_archive(tmp_path, monkeypatch)
    vendor = tmp_path / "editor_web/vendor"
    vendor.mkdir(parents=True)
    (vendor / "previous.txt").write_text("preserve old installation")
    original = Path.rename
    def failing_rename(self, target):
        if self.name == "vendor" and self.parent.name == "verify":
            raise OSError("injected interrupted replacement")
        return original(self, target)
    monkeypatch.setattr(Path, "rename", failing_rename)
    with pytest.raises(OSError, match="interrupted replacement"):
        fetch_monaco.main()
    assert (vendor / "previous.txt").read_text() == "preserve old installation"
    assert not list(vendor.parent.glob(".vendor-backup-*"))


def test_monaco_fetch_refuses_to_replace_vendor_symlink(tmp_path, monkeypatch):
    configure_archive(tmp_path, monkeypatch)
    outside = tmp_path / "unrelated"
    outside.mkdir()
    (outside / "important.txt").write_text("preserve")
    (tmp_path / "editor_web").mkdir()
    try:
        (tmp_path / "editor_web/vendor").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not permit symlink creation")
    with pytest.raises(RuntimeError, match="symbolic-linked"):
        fetch_monaco.main()
    assert (outside / "important.txt").read_text() == "preserve"
