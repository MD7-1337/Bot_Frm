import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Real Qt/Monaco alpha workflow")
def test_managed_project_debug_scheduled_simulation_and_restart(tmp_path):
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "tests/probe_alpha_completion.py"), str(tmp_path)]
    if screenshots := os.environ.get("STUDIO_SCREENSHOT_DIR"):
        command.append(screenshots)
    env = dict(os.environ, STUDIO_CONFIG_DIR=str(tmp_path / "config"), STUDIO_DATA_DIR=str(tmp_path / "data"))
    try:
        result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=100)
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b""
        errors = error.stderr or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        if isinstance(errors, bytes):
            errors = errors.decode("utf-8", errors="replace")
        pytest.fail(f"Native GUI workflow timed out.\n{output}\n{errors}")
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("managed_project", "captured_target", "gutter_breakpoint", "debug_variables", "debug_step", "recorded_python", "scheduled_worker", "durable_history", "archive_restore", "restart_revokes_trust"):
        assert f'"{check}": true' in result.stdout
