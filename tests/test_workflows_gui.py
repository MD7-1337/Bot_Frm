import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.mark.gui
@pytest.mark.skipif(os.environ.get('STUDIO_GUI_TESTS')!='1',reason='Real native group/workflow editor')
def test_native_group_workflow_editor_and_actual_workers(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'tests/probe_workflows.py'),str(tmp_path)],cwd=root,env=dict(os.environ),capture_output=True,text=True,timeout=35)
    assert result.returncode==0,result.stdout+result.stderr
    for name in ('native_group_expansion','ordered_editor','actual_independent_workers','durable_occurrence_history','restart_revokes_workflow_approval'):
        assert f'"{name}": true' in result.stdout
