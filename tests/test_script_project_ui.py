import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires Qt widget integration")
def test_explicit_project_and_save_error_cleanup(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_script_project_ui.py"), str(tmp_path)],
                            cwd=root, env=dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "settings")),
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"project": true' in result.stdout
    assert '"save_error": true' in result.stdout
    assert '"cleanup": true' in result.stdout
