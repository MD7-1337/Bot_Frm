import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.editor.assets import MonacoAssetsError, validate_monaco
from app.health import dependency_health


def vendor_fixture(tmp_path):
    path = tmp_path / "vendor/vs/loader.js"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"known pinned distribution")
    manifest = {"version": "fixture", "files": {"vs/loader.js": {
        "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}}
    return path, manifest


def test_monaco_verifies_bytes_instead_of_file_existence(tmp_path):
    path, manifest = vendor_fixture(tmp_path)
    assert validate_monaco(tmp_path, manifest=manifest)["files_verified"] == 1
    # A same-size corrupt loader used to be accepted and cause require undefined.
    path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises(MonacoAssetsError, match="corrupt or wrong version"):
        validate_monaco(tmp_path, manifest=manifest)


def test_monaco_missing_asset_has_supported_repair(tmp_path):
    path, manifest = vendor_fixture(tmp_path)
    path.unlink()
    with pytest.raises(MonacoAssetsError, match="fetch_monaco.py"):
        validate_monaco(tmp_path, manifest=manifest)


def test_monaco_rejects_self_referential_link_without_loop(tmp_path):
    vendor = tmp_path / "vendor"
    try:
        vendor.symlink_to(vendor, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("This host cannot create symlinks")
    with pytest.raises(MonacoAssetsError, match="symbolic link"):
        validate_monaco(tmp_path, manifest={"version": "fixture", "files": {}})


def test_health_missing_dependencies_is_actionable_json(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(importlib.metadata, "version", missing)
    monkeypatch.setattr("app.health.shutil.which", lambda path: None)
    report = dependency_health(native=False)
    assert not report["ok"]
    assert len([item for item in report["checks"] if item["name"] in ("PySide6", "numpy", "av", "opencv-python-headless") and item["status"] == "failed"]) == 4
    assert report["physical_android"] == "NOT VERIFIED"
    json.dumps(report, allow_nan=False)


def test_health_cli_works_even_when_site_packages_are_unavailable():
    result = subprocess.run([sys.executable, "-S", "-m", "app.main", "--health"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert not report["ok"]
    assert any(item["name"] == "PySide6" and item["status"] == "failed" for item in report["checks"])


def test_breakpoint_bridge_accepts_only_bounded_source_metadata():
    from app.editor.bridge import EditorBridge
    bridge = EditorBridge()
    observed = []
    bridge.breakpoints_changed.connect(observed.append)
    bridge.breakpointsChanged("[3, 1, 3]")
    assert observed == [[1, 3]]
    for invalid in ("{}", "[0]", "[true]", "[1.5]", "[\"3\"]", "x", "[" + ",".join("1" for _ in range(1001)) + "]"):
        bridge.breakpointsChanged(invalid)
    assert observed == [[1, 3]]


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Opt-in real local WebEngine startup tests")
@pytest.mark.parametrize("mode", ["missing", "corrupt", "normal"])
def test_editor_readiness_and_breakpoint_metadata(tmp_path, mode):
    result = subprocess.run([sys.executable, "tools/probe_editor_reliability.py", str(tmp_path), mode],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["verified"] is True
