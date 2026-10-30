import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Set STUDIO_GUI_TESTS=1 with desktop or documented headless Qt setup")
def test_real_qt_ui_leases_preview_threads_and_shutdown(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path))
    result = subprocess.run([sys.executable, str(root / "tests/probe_ui_safety.py")], cwd=root,
                            env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("leases", "emergency_manual", "preview_png_gestures", "job_gui_thread", "shutdown"):
        assert f'"{check}": true' in result.stdout
