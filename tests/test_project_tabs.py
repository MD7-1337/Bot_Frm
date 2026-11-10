import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Real Qt/Monaco tab integration")
def test_independent_tab_breakpoints_survive_switch_save_and_close(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_project_tabs.py"), str(tmp_path)],
                            cwd=root, capture_output=True, text=True, timeout=35,
                            env=dict(os.environ, STUDIO_DATA_DIR=str(tmp_path / "data"),
                                     STUDIO_CONFIG_DIR=str(tmp_path / "config")))
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"tab_breakpoints": true' in result.stdout
