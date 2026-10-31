"""Recorder tickets verify no phantom actions, crossover, stale replay or execution."""
import ast

import pytest

from app.automation.recording import ActionRecorder
from app.automation.runtime import RuntimeCoordinator
from test_script_runtime import completed


def test_successful_actions_and_idle_delays_generate_valid_python():
    recorder = ActionRecorder()
    recorder.start("phone-one", 1)
    ticket = recorder.ticket("phone-one", 1, "tap(10, 20)")
    assert recorder.actions == []
    recorder.complete(ticket, 100)
    recorder.complete(recorder.ticket("phone-one", 1, "swipe(10, 20, 30, 40, duration=0.5)", .5), 100.4)
    recorder.complete(recorder.ticket("phone-one", 1, "home()"), 100.91)
    recorder.stop()
    assert recorder.actions == ["tap(10, 20)", "sleep(0.400)", "swipe(10, 20, 30, 40, duration=0.5)", "home()"]
    ast.parse(recorder.source())


def test_other_devices_or_connection_generations_are_ignored():
    recorder = ActionRecorder()
    recorder.start("phone-one", 3)
    assert recorder.ticket("phone-two", 3, "home()") is None
    assert recorder.ticket("phone-one", 2, "home()") is None
    recorder.complete(None, 10)
    assert recorder.actions == []


def test_pausing_invalidates_pending_completions_and_excludes_paused_delay():
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "home()"), 1)
    ticket = recorder.ticket("phone", 1, "back()")
    recorder.pause()
    recorder.resume("phone", 1)
    recorder.complete(ticket, 2)
    recorder.complete(recorder.ticket("phone", 1, "tap(1, 2)"), 900)
    assert recorder.actions == ["home()", "tap(1, 2)"]


@pytest.mark.parametrize("reason", ["Emergency stop", "Device disconnected", "Window closing"])
def test_stopped_and_replaced_sessions_reject_old_tickets(reason):
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    ticket = recorder.ticket("phone", 1, "home()")
    recorder.stop(reason)
    recorder.complete(ticket, 10)
    assert recorder.reason == reason and not recorder.actions
    recorder.start("phone", 2)
    recorder.complete(ticket, 20)
    assert not recorder.actions


def test_failure_stops_recording_without_claiming_action_completed():
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "home()"), None, "ADB timed out")
    assert recorder.state == "stopped"
    assert "uncertain" in recorder.reason and recorder.actions == []


def test_timeline_limit_never_partially_appends_delay():
    recorder = ActionRecorder(limit=2)
    recorder.start("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "home()"), 1)
    recorder.complete(recorder.ticket("phone", 1, "back()"), 2)
    assert recorder.state == "stopped" and recorder.actions == ["home()"]


@pytest.mark.parametrize("code", ["x = 1", "home(); back()", "if True:\n home()", "tap(", "", "x" * 4097])
def test_invalid_timeline_edits_are_not_generated(code):
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    recorder.stop()
    recorder.actions = [code]
    with pytest.raises(ValueError):
        recorder.source()


def test_start_and_resume_require_same_verified_connection():
    recorder = ActionRecorder()
    with pytest.raises(ValueError):
        recorder.start("phone", 0)
    with pytest.raises(ValueError):
        recorder.start("phone\nother", 1)
    recorder.start("phone", 1)
    with pytest.raises(ValueError):
        recorder.start("other", 1)
    recorder.pause()
    with pytest.raises(ValueError):
        recorder.resume("phone", 2)
    with pytest.raises(ValueError):
        recorder.resume("other", 1)


def test_generated_recording_replays_in_two_independent_spawned_workers(tmp_path):
    recorder = ActionRecorder()
    recorder.start("recorded-phone", 1)
    for index, code in enumerate(("tap(10, 20)", "doubleClick(Location(3, 4), interval=0)", "longPress(Location(5, 6), duration=.01)", "home()", "back()")):
        recorder.complete(recorder.ticket("recorded-phone", 1, code), index * .01)
    recorder.stop()
    with RuntimeCoordinator(max_workers=2) as runtime:
        ids = [runtime.start(recorder.source(), serial, trusted=True, project_root=tmp_path)
               for serial in ("replay-one", "replay-two")]
        events = completed(runtime, ids)
        assert all(run.state == "completed" for run in runtime.snapshot()), events
        for serial in ("replay-one", "replay-two"):
            commands = [item for item in events if item.get("serial") == serial and item.get("command") in ("tap", "swipe", "key")]
            assert [item["command"] for item in commands] == ["tap", "tap", "tap", "swipe", "key", "key"]


def screenshot_evidence(serial='phone'):
    import cv2
    import numpy as np
    from app.automation.recording import ScreenshotEvidence
    pixels = np.random.default_rng(5).integers(0,255,(60,90,3),np.uint8)
    return ScreenshotEvidence(serial,cv2.imencode('.png',pixels)[1].tobytes(),(90,60))


def test_schema_two_preserves_preaction_evidence_geometry_and_duration():
    import json
    recorder=ActionRecorder()
    recorder.start('phone',1)
    evidence=screenshot_evidence()
    recorder.complete(recorder.ticket('phone',1,'tap(40, 30)',.2),10,evidence=evidence)
    recorder.stop()
    payload=recorder.session_json()
    restored=ActionRecorder(); restored.load_session(payload)
    assert restored.actions==['tap(40, 30)']
    assert restored.evidence=={0:evidence}
    assert restored.durations=={0:.2}
    assert restored.screen_size==(90,60)
    assert json.loads(payload)['schema_version']==3
    assert ast.parse(restored.source())


def test_failed_or_stale_actions_never_keep_screenshot_evidence():
    recorder=ActionRecorder(); recorder.start('phone',1)
    ticket=recorder.ticket('phone',1,'tap(40, 30)')
    recorder.pause(); recorder.resume('phone',1)
    recorder.complete(ticket,10,evidence=screenshot_evidence())
    assert recorder.evidence=={}
    recorder.complete(recorder.ticket('phone',1,'tap(40, 30)'),11,'failed',evidence=screenshot_evidence())
    assert recorder.actions==[] and recorder.evidence=={}


def test_other_device_evidence_does_not_attach():
    recorder=ActionRecorder(); recorder.start('phone',1)
    recorder.complete(recorder.ticket('phone',1,'tap(1, 2)'),10,evidence=screenshot_evidence('other'))
    assert recorder.actions==['tap(1, 2)'] and not recorder.evidence


@pytest.mark.parametrize('change',[
    lambda d:d.update(evidence={'1':d['evidence']['0']}),
    lambda d:d['evidence']['0'].update(size=[2,3]),
    lambda d:d['evidence']['0'].update(png='invalid!'),
    lambda d:d.update(durations={'0':-1}),
    lambda d:d.update(durations={'0':10**400}),
    lambda d:d.update(screen_size=[True,4]),
])
def test_bad_session_is_transactional(change):
    import json
    recorder=ActionRecorder(); recorder.start('phone',1)
    recorder.complete(recorder.ticket('phone',1,'tap(1, 2)'),10,evidence=screenshot_evidence())
    recorder.stop()
    original=recorder.session_json(); data=json.loads(original); change(data)
    with pytest.raises(ValueError): recorder.load_session(json.dumps(data))
    assert recorder.session_json()==original


def test_conversion_keeps_original_target_offset_and_valid_python():
    from app.automation.recording import image_target_code
    from app.vision.matching import Region
    code=image_target_code('tap(40, 30)',Region(20,10,40,40),'images/start.png')
    assert code=='click("images/start.png")'
    code=image_target_code('tap(43, 27)',Region(20,10,40,40),'images/a"b.png')
    assert '.targetOffset(3, -3)' in code
    ast.parse(code)
    for invalid in ('home()', 'tap(x, y)', 'tap(True, 2)', 'tap(2, 3); back()', 'tap(2, 3, extra=1)'):
        with pytest.raises(ValueError): image_target_code(invalid,Region(0,0,80,50),'target.png')
    with pytest.raises(ValueError,match='contain'): image_target_code('tap(90, 30)',Region(0,0,80,50),'target.png')


def test_elapsed_timestamps_survive_save_pause_and_load_while_pause_is_excluded_from_delay():
    import json
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "home()"), 100)
    recorder.pause()
    recorder.resume("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "back()"), 200)
    recorder.stop()
    assert recorder.actions == ["home()", "back()"]
    assert recorder.timestamps == {0: 0., 1: 100.}
    restored = ActionRecorder()
    restored.load_session(recorder.session_json())
    assert restored.timestamps == recorder.timestamps
    assert json.loads(recorder.session_json())["schema_version"] == 3


def test_schema_two_still_loads_without_invented_timestamps():
    import json
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "home()"), 100)
    recorder.stop()
    data = json.loads(recorder.session_json())
    data["schema_version"] = 2
    data.pop("timestamps")
    restored = ActionRecorder()
    restored.load_session(json.dumps(data))
    assert restored.actions == recorder.actions and restored.timestamps == {}


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), True, None, -1, 10**400])
def test_bad_recording_clock_never_appends_an_action(timestamp):
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "home()"), timestamp)
    assert recorder.state == "stopped" and recorder.actions == []


@pytest.mark.parametrize("timestamps", [{"0": float("nan")}, {"1": 2}, {"0": -1}, {"0": True}, []])
def test_bad_persisted_timestamps_are_transactional(timestamps):
    import json
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    recorder.complete(recorder.ticket("phone", 1, "home()"), 100)
    recorder.stop()
    before = recorder.session_json()
    data = json.loads(before)
    data["timestamps"] = timestamps
    with pytest.raises(ValueError):
        recorder.load_session(json.dumps(data))
    assert recorder.session_json() == before
