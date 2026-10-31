"""Central native integration; declared registry fixtures are not phone tests."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Real workbench/Monaco connection wizard")
@pytest.mark.parametrize("scale", ["1", "1.25"])
def test_workbench_connection_wizard_stale_input_and_compact_workspaces(tmp_path, scale):
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "tests/probe_connection_workbench.py"), str(tmp_path)]
    if directory := os.environ.get("STUDIO_SCREENSHOT_DIR"):
        command.append(directory)
    env = dict(os.environ, QT_SCALE_FACTOR=scale, STUDIO_CONFIG_DIR=str(tmp_path / "config"),
               STUDIO_DATA_DIR=str(tmp_path / "data"))
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("monaco_ready", "central_wizard", "report_generation", "stale_home_rejected",
                  "compact_workspaces", "wizard_cleanup"):
        assert f'"{check}": true' in result.stdout
