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
