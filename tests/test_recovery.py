"""Typed failure advice and actual spawned failure events; no action replay."""
import pytest
from app.automation.api import errors
from app.automation.recovery import classify_failure
from app.automation.runtime import RuntimeCoordinator
from app.simulation.model import SimulationManager
from app.simulation.project import create_project
from test_script_runtime import completed


@pytest.mark.parametrize('error,category',[
    (errors.DeviceUnauthorized('locked'),'device_connection'),
    (errors.DeviceOffline('offline'),'device_connection'),
    (errors.DeviceDisconnected('gone'),'device_connection'),
    (errors.CommandTimeout('unknown'),'input_outcome_unknown'),
    (errors.CommandFailed('failed'),'input_outcome_unknown'),
    (errors.RecognitionTimeout('late'),'recognition'),
    (errors.ImageNotFound('absent'),'recognition'),
    (errors.AmbiguousMatch('two'),'recognition'),
    (errors.FrameUnavailable('frame'),'frame_capture'),
    (errors.AssetNotFound('missing'),'image_asset'),
    (errors.InvalidAsset('bad'),'image_asset'),
    (errors.OCRUnavailable('not installed'),'ocr_dependency'),
    (errors.OCRFailed('engine'),'ocr_engine'),
    (errors.InvalidCoordinates('outside'),'target_geometry'),
    (errors.CrossDeviceTarget('other'),'target_geometry'),
    (errors.UnsupportedCapability('no packages'),'unsupported'),
    (AssertionError('bad value'),'python'),
    # Message alone must never classify a Python exception as a device fault.
    (ValueError('DeviceDisconnected'),'python'),
])
def test_typed_classification_never_authorizes_automatic_retry(error,category):
    result=classify_failure(error)
    assert result['category']==category
    assert result['automatic_retry'] is False and result['advice']


def test_spawned_recognition_failure_has_source_and_advice_without_replay(tmp_path):
    manager=SimulationManager()
    try:
        info=manager.create();root,_=create_project(tmp_path,info.serial,'image')
        with RuntimeCoordinator() as runtime:
            run=runtime.start('# failure fixture\nwaitImage("reward.png", timeout=.05)\n',info.serial,
                              backend='simulation',simulation_config=manager.config(info.serial),trusted=True,project_root=root,script_id='<failure-fixture>')
            events=completed(runtime,[run])
            error=next(e for e in events if e['event']=='error')
            assert error['error_type']=='RecognitionTimeout'
            assert error['source_path']=='<failure-fixture>' and error['source_line']==2
            assert error['failure']['category']=='recognition'
            assert error['failure']['automatic_retry'] is False
            assert len(runtime.snapshot())==1 and runtime.snapshot()[0].state=='failed'
            assert manager.client(info.serial).state()['actions']==0
    finally:manager.close()
