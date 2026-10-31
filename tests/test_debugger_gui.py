import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Opt-in real Qt debugger worker journey")
def test_actual_qt_debug_controls_variables_and_worker(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_debugger.py"), str(tmp_path)],
                            cwd=root, capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("debugger_panel", "actual_worker", "variables", "step_over", "continue"):
        assert f'"{check}": true' in result.stdout
