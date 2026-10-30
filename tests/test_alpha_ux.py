import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires real Qt/Monaco GUI")
def test_visible_alpha_connection_capture_script_recorder_and_settings_journey(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_alpha_ux.py"), str(tmp_path)],
                            cwd=root, env=dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "settings"), STUDIO_CONFIG_DIR=str(tmp_path / "settings")),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("permissions_diagnostics", "visible_controls", "preview", "capture_crop_insert_match", "script_run_pause_stop", "recorder_session_replay", "tabs", "themes", "responsive", "cleanup"):
        assert f'"{check}": true' in result.stdout
