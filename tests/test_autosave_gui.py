import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Real Monaco process crash and native draft recovery")
def test_actual_autosave_process_loss_and_native_recovery(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, STUDIO_DATA_DIR=str(tmp_path / "data"), STUDIO_CONFIG_DIR=str(tmp_path / "config"))
    for mode in ("crash", "recover"):
        result = subprocess.run([sys.executable, str(root / "tests/probe_autosave_recovery.py"), str(tmp_path), mode],
                                cwd=root, env=environment, capture_output=True, text=True, timeout=40)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'true' in result.stdout
