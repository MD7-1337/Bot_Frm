"""Cross-platform delivery guards; actual Windows execution is tested in CI."""
import importlib.util
import json
import os
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


def test_extracted_windows_smoke_uses_relocated_payload_without_source_environment(tmp_path, monkeypatch):
    builder = module("build_windows")
    archive = tmp_path / "portable.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("AndroidAutomationStudio/AndroidAutomationStudio.exe", b"test fixture, not a Windows application")
    report = tmp_path / "smoke.json"
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.setenv("PYTHONHOME", "source-runtime")
    monkeypatch.setenv("STUDIO_TEST_GUARD", "preserved")
    calls = []

    def run(arguments, *, cwd, env, timeout, check):
        calls.append(arguments)
        executable = Path(arguments[0])
        assert executable.read_bytes().startswith(b"test fixture")
        assert "studio extracted Windows " in str(executable)
        assert not executable.is_relative_to(ROOT)
        assert Path(cwd) != ROOT
        assert "PYTHONPATH" not in env and "PYTHONHOME" not in env
        assert env["STUDIO_TEST_GUARD"] == "preserved"
        assert check and timeout > 0
        Path(arguments[2]).write_text(json.dumps({"passed": True, "frozen": True}))

    monkeypatch.setattr(builder.subprocess, "run", run)
    assert builder.verify_extracted_zip(archive, report)["passed"]
    assert len(calls) == 1
    assert not Path(calls[0][0]).exists()  # Owned temporary extraction cleaned up.


def test_windows_smoke_rejects_nonfrozen_success_report(tmp_path, monkeypatch):
    builder = module("build_windows")
    archive = tmp_path / "portable.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("AndroidAutomationStudio/AndroidAutomationStudio.exe", b"fixture")
    report = tmp_path / "smoke.json"
    monkeypatch.setattr(builder.subprocess, "run", lambda args, **kwargs: report.write_text('{"passed":true,"frozen":false}'))
    with pytest.raises(RuntimeError, match="frozen smoke"):
        builder.verify_extracted_zip(archive, report)


def test_installer_requires_explicitly_installed_compiler(tmp_path, monkeypatch):
    builder = module("build_windows")
    monkeypatch.setattr(builder.shutil, "which", lambda _: None)
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    with pytest.raises(RuntimeError, match="compiler not found"):
        builder.build_installer("0.2.0")


def test_ci_failure_annotations_escape_control_characters_and_preserve_counts(tmp_path, monkeypatch, capsys):
    reporter = module("ci_test_report")
    source = tmp_path / "tests.xml"
    source.write_text('<testsuites><testsuite><testcase name="ok"/><testcase name="bad"><failure message="x% y&#10;::error::injected"/></testcase><testcase name="skip"><skipped/></testcase></testsuite></testsuites>')
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert reporter.publish(source) == 1
    output = capsys.readouterr().out
    assert output.count("\n") == 2
    assert output.startswith("::notice title=Source regression totals::1 passed, 1 failed/error, 1 skipped.")
    assert output.splitlines()[1].startswith("::error title=Regression failure::")
    assert "x%25 y%0A::error::injected" in output
    assert "1 passed, 1 failed/error, 1 skipped" in summary.read_text()
