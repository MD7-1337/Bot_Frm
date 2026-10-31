"""Portable integrity, real frozen-resource lookup and worker smoke contracts."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from app.devices.paths import adb_executable
from app.release_checks import simulation_smoke
from app.resources import resource_root
from app.streaming.manager import StreamManager

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("studio_build_windows", ROOT / "tools/build_windows.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_frozen_resource_paths_and_explicit_external_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("STUDIO_ADB", raising=False)
    monkeypatch.delenv("STUDIO_SCRCPY_SERVER", raising=False)
    monkeypatch.setattr("app.devices.paths.shutil.which", lambda name: None)
    executable = tmp_path / ".tools/platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture executable")
    assert resource_root() == tmp_path
    assert adb_executable() == str(executable)
    assert StreamManager().server_path == tmp_path / ".tools/scrcpy-server-v3.1"
    monkeypatch.setenv("STUDIO_ADB", str(tmp_path / "external adb"))
    assert adb_executable() == str(tmp_path / "external adb")


def test_portable_zip_has_stable_contained_layout_and_matching_checksum(tmp_path):
    payload = tmp_path / "AndroidAutomationStudio"
    resources = payload / "_internal/editor_web"
    resources.mkdir(parents=True)
    (payload / "AndroidAutomationStudio.exe").write_bytes(b"fixture only")
    (resources / "index.html").write_text("<html>fixture</html>")
    target = tmp_path / "portable.zip"
    digest = builder.create_portable_zip(payload, target)
    assert digest == hashlib.sha256(target.read_bytes()).hexdigest()
    assert target.with_suffix(".zip.sha256").read_text().strip() == f"{digest}  portable.zip"
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {
            "AndroidAutomationStudio/AndroidAutomationStudio.exe",
            "AndroidAutomationStudio/_internal/editor_web/index.html",
        }
    with pytest.raises(FileExistsError):
        builder.create_portable_zip(payload, target)


def test_portable_zip_rejects_linked_payload_before_writing(tmp_path):
    payload = tmp_path / "payload"
    payload.mkdir()
    outside = tmp_path / "secret"
    outside.write_text("must not escape into distribution")
    try:
        (payload / "link").symlink_to(outside)
    except OSError:
        pytest.skip("Host does not permit symbolic link creation")
    target = tmp_path / "portable.zip"
    with pytest.raises(ValueError, match="symbolic"):
        builder.create_portable_zip(payload, target)
    assert not target.exists()


def test_release_simulation_smoke_runs_actual_worker_and_pixels(tmp_path):
    result = simulation_smoke(tmp_path)
    assert result["passed"] is True
    assert result["independent_pids"] == 1
    assert result["android_hardware"] == "NOT VERIFIED"
    assert result["elapsed_seconds"] > 0


def test_release_simulation_smoke_runs_four_independent_workers(tmp_path):
    result = simulation_smoke(tmp_path, count=4)
    assert result["devices"] == result["independent_pids"] == 4
    assert result["passed"] is True


def test_build_refuses_linux_without_creating_fake_windows_artifact(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["build_windows.py"])
    monkeypatch.setattr(builder.platform, "system", lambda: "Linux")
    with pytest.raises(SystemExit) as failure:
        builder.main()
    assert failure.value.code == 2


def test_scheduler_iana_timezones_work_without_system_timezone_database():
    # Windows does not supply the Unix IANA tzdb. Exercise tzdata fallback in a
    # fresh interpreter so previous ZoneInfo caches cannot conceal missing data.
    script = '''
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from app.tasks.store import Task, next_due
zone = ZoneInfo("America/New_York")
assert datetime(2026, 7, 1, tzinfo=zone).utcoffset().total_seconds() == -14400
task = Task(task_id="timezone-fixture", name="Daily", source="pass", serial="fixture",
            script_id="<script>", project_root=str(Path.cwd()), schedule="daily", at="09:00",
            timezone="America/New_York")
task.validate()
due = next_due(task, datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc))
assert due == datetime(2026, 7, 1, 13, 0, tzinfo=timezone.utc).timestamp()
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                            env={**os.environ, "PYTHONTZPATH": ""}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
