import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Set STUDIO_GUI_TESTS=1 with desktop or headless Qt setup")
def test_capture_selection_crop_save_and_fresh_match(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path), STUDIO_CONFIG_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, str(root / "tests/probe_capture_dialog.py"), str(tmp_path)],
                            cwd=root, env=environment, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("selection", "save", "reference", "match", "ambiguous", "no_match", "errors", "async", "frozen"):
        assert f'"{check}": true' in result.stdout
