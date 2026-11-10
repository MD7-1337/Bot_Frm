import os
from pathlib import Path
import subprocess
import sys
import pytest

# The old journey requires visible Recorder and workspace navigation. Backend
# behavior remains covered by the dedicated recording/runtime/simulation tests.
pytestmark = pytest.mark.skip(reason="Retired workspace journey; backend and approved UI have replacement tests")


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get('STUDIO_GUI_TESTS')!='1',reason='Opt-in real Qt/Monaco simulator journey')
def test_real_demo_controls_recognition_recording_and_worker_journey(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'tests/probe_phase6.py'),str(tmp_path)],cwd=root,
                          env=dict(os.environ,STUDIO_DATA_DIR=str(tmp_path/'data'),STUDIO_CONFIG_DIR=str(tmp_path/'settings')),
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    for check in ('demo_start','isolated_workers','recognition_inspector','pixel_insertion','recorder_conversion','recorder_replay','pause_resume','emergency_stop','independent_simulations','strict_adb_isolation','themes','responsive','failure_inspection'):
        assert f'"{check}": true' in result.stdout
