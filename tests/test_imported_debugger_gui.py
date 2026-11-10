import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get('STUDIO_GUI_TESTS') != '1', reason='Real Monaco/imported debugger journey')
def test_imported_debugger_and_persistent_monaco_breakpoints(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'tests/probe_imported_debugger.py'), str(tmp_path)],
                            cwd=root, capture_output=True, text=True, timeout=50)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ('imported_debugger','frame_hash_navigation','persistent_breakpoints','actual_worker'):
        assert f'"{check}": true' in result.stdout


@pytest.mark.skip(reason="Retired visible debugger and demo navigation; imported debugger backend test remains active")
@pytest.mark.gui
@pytest.mark.skipif(os.environ.get('STUDIO_GUI_TESTS') != '1', reason='Real imported-source workbench navigation')
def test_workbench_imported_frame_navigation_preserves_stale_edits(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, STUDIO_DATA_DIR=str(tmp_path / 'data'), STUDIO_CONFIG_DIR=str(tmp_path / 'config'))
    result = subprocess.run([sys.executable, str(root / 'tests/probe_imported_window.py')],
                            cwd=root, capture_output=True, text=True, timeout=50, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ('imported_window_navigation','stale_disk_refused','dirty_tab_preserved','paused_worker_stop'):
        assert f'"{check}": true' in result.stdout
