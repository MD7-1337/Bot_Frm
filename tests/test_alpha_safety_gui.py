import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get('STUDIO_GUI_TESTS')!='1',reason='Opt-in real StudioWindow/Monaco safety journeys')
@pytest.mark.parametrize('mode,checks',[
    ('corrupt',('corrupt_databases_preserved','monaco_editing_after_corruption')),
    ('stale',('run_approval_rejects_reset_connection','task_approval_rejects_reset_connection')),
    ('evidence',('actual_worker_failure_persisted','fresh_postfailure_capture_preserves_identity')),
])
def test_integrated_alpha_safety(tmp_path,mode,checks):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'tests/probe_alpha_safety.py'),str(tmp_path),mode],cwd=root,
                          capture_output=True,text=True,timeout=60,env=dict(os.environ))
    assert result.returncode==0,result.stdout+result.stderr
    for check in checks:assert f'"{check}": true' in result.stdout
