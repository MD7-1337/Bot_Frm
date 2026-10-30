import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires real desktop/headless Qt WebEngine")
def test_editor_workers_shared_assigned_pause_resume_and_errors(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_script_workbench.py"), str(tmp_path)],
                            cwd=root, env=dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "settings"), STUDIO_CONFIG_DIR=str(tmp_path / "settings")),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("shared", "assigned", "pause_resume", "stop", "errors", "execution_line", "cleanup"):
        assert f'"{check}": true' in result.stdout
