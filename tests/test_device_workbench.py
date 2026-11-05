import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires opt-in desktop/headless Qt integration")
def test_multidevice_video_control_capture_editor_and_disconnect(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_device_workbench.py"), str(tmp_path)],
                            cwd=root, env=dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "settings"), STUDIO_CONFIG_DIR=str(tmp_path / "settings")),
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("two_previews", "serial_control", "capture_monaco", "fresh_match", "disconnect", "discovery_error", "cleanup"):
        assert f'"{check}": true' in result.stdout
