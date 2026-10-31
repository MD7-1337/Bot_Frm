import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get('STUDIO_GUI_TESTS')!='1',reason='Opt-in native task management and real simulation worker journey')
def test_native_tasks_create_approve_run_and_persist(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'tests/probe_tasks.py'),str(tmp_path)],cwd=root,
                          capture_output=True,text=True,timeout=30,env=dict(os.environ))
    assert result.returncode==0,result.stdout+result.stderr
    assert '"native_task_controls": true' in result.stdout
    assert '"real_worker_screen_change": true' in result.stdout
    assert '"persistent_history": true' in result.stdout
