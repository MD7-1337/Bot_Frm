import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires Qt/Monaco integration")
def test_device_manager_visual_library_and_recorder_workflow(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_visual_workspaces.py"), str(tmp_path)],
                            cwd=root, env=dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "settings"), STUDIO_CONFIG_DIR=str(tmp_path / "settings")),
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("navigation", "selection", "groups", "network", "visual_library", "fresh_match", "full_resolution", "recorder", "disconnect", "cleanup"):
        assert f'"{check}": true' in result.stdout
