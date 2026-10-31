import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Opt-in real Qt recovery history and recorder journey")
def test_persistent_failure_widgets_and_recorder_metadata_controls(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_recovery.py"), str(tmp_path)],
                            cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("failure_history", "private_evidence", "recorder_metadata"):
        assert f'"{check}": true' in result.stdout
