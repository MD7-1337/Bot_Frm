"""Real spawned scripting workers against explicit image/device fixtures."""
from pathlib import Path
import time

import cv2
import numpy as np
import pytest

from app.automation.runtime import RuntimeCoordinator


def drain_until(runtime, predicate, timeout=10):
    events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events.extend(runtime.poll())
        if predicate(events, runtime.snapshot()):
            return events
        time.sleep(.005)
    pytest.fail(f"Script workers did not reach expected state: {runtime.snapshot()} {events[-5:]}")


def completed(runtime, ids):
    return drain_until(runtime, lambda events, runs: set(ids) <= {run.run_id for run in runs if run.exitcode is not None})


def write_png(path: Path, rgb):
    path.write_bytes(cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))[1].tobytes())


@pytest.fixture
def image_project(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "project.json").write_text('{"schema_version":1}', encoding="utf-8")
    rng = np.random.default_rng(127)
    template = rng.integers(0, 255, (9, 11, 3), dtype=np.uint8)
    blank = np.zeros((80, 100, 3), np.uint8)
    screen = blank.copy()
    screen[20:29, 30:41] = template
    write_png(tmp_path / "images/start.png", template)
    write_png(tmp_path / "blank.png", blank)
    write_png(tmp_path / "screen.png", screen)
    return tmp_path


def test_image_api_two_styles_run_in_independent_spawn_contexts(image_project):
    root = image_project
    source = ("assert getDevice() == device.serial\n"
              "match = waitImage(Pattern('start.png').similar(.99), timeout=.5)\n"
              "assert isinstance(match, Match)\n"
              "point = click(match)\n"
              "assert point == Location(35, 24)\n"
              "device.doubleClick(Location(2,3), interval=0)\n"
              "assert device.getResolution() == (100,80)\n"
              "assert device.capture().width == 100\n"
              "wait(0)\nprint(device.serial)\n")
    config = {"frame_paths": [str(root / "screen.png")]}
    with RuntimeCoordinator(max_workers=2) as runtime:
        one = runtime.start(source, "fixture-one", trusted=True, project_root=root, mock_config=config)
        two = runtime.start(source, "fixture-two", trusted=True, project_root=root, mock_config=config)
        events = completed(runtime, [one, two])
        assert all(run.state == "completed" for run in runtime.snapshot()), events
        taps = [event for event in events if event.get("command") == "tap"]
        assert len(taps) == 6
        assert {event["serial"] for event in taps} == {"fixture-one", "fixture-two"}
        for serial in ("fixture-one", "fixture-two"):
            assert [(event["arguments"]["x"], event["arguments"]["y"]) for event in taps if event["serial"] == serial] == [(35,24), (2,3), (2,3)]
        assert len({run.pid for run in runtime.snapshot()}) == 2


def test_project_imports_normal_python_and_traceback_locations(image_project):
    root = image_project
    helper = root / "scripts/helpers.py"
    helper.write_text("from app.automation.api import click\ndef run():\n    return click('start.png')\n", encoding="utf-8")
    source = ("from helpers import run\n"
              "points=[]\n"
              "for value in range(2):\n    points.append(run())\n"
              "if len(points) == 2:\n    print('imports-ok')\n"
              "elif points:\n    raise AssertionError('bad branch')\n"
              "else:\n    raise AssertionError('no points')\n"
              "try:\n    find('missing.png')\nexcept AssetNotFound:\n    print('caught-missing')\n")
    config = {"frame_paths": [str(root / "screen.png")]}
    old_cwd = Path.cwd()
    with RuntimeCoordinator() as runtime:
        success = runtime.start(source, "fixture-one", trusted=True, script_id=str(root / "scripts/main.py"), mock_config=config)
        events = completed(runtime, [success])
        assert runtime.snapshot()[0].state == "completed", events
        output = "".join(event["text"] for event in events if event["event"] == "output")
        assert "imports-ok" in output and "caught-missing" in output
        assert any(event["event"] == "line" for event in events)
        failure = runtime.start("x=1\nraise RuntimeError('expected failure')\n", "fixture-one", trusted=True,
                                script_id=str(root / "scripts/bad.py"), project_root=root)
        failures = completed(runtime, [failure])
        error = next(event for event in failures if event["event"] == "error" and event["run_id"] == failure)
        assert error["source_line"] == 2
        assert error["source_path"] == str(root / "scripts/bad.py")
        assert "RuntimeError: expected failure" in error["traceback"]
    assert Path.cwd() == old_cwd


def test_pause_busy_python_resume_and_cancel_preserve_device_lease(image_project):
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start("count=0\nwhile True:\n    count += 1\n", "fixture-one", trusted=True,
                               project_root=image_project)
        drain_until(runtime, lambda events, runs: any(event.get("state") == "running" for event in events))
        runtime.pause(run_id)
        drain_until(runtime, lambda events, runs: runs[0].state == "paused")
        assert runtime.snapshot()[0].exitcode is None
        time.sleep(.08)
        assert runtime.snapshot()[0].state == "paused"
        runtime.resume(run_id)
        drain_until(runtime, lambda events, runs: any(event.get("state") == "running" for event in events))
        runtime.pause(run_id)
        drain_until(runtime, lambda events, runs: runs[0].state == "paused")
        runtime.cancel(run_id, grace=.2)
        completed(runtime, [run_id])
        assert runtime.snapshot()[0].state == "cancelled"


def test_appearance_and_vanish_waits_use_real_fixture_frames(image_project):
    root = image_project
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start("m=wait('start.png', timeout=1)\nwaitVanish('start.png', timeout=1)\nprint('vanished')",
                               "fixture-one", trusted=True, project_root=root,
                               mock_config={"frame_paths": [str(root / "blank.png"), str(root / "screen.png"), str(root / "blank.png")]})
        events = completed(runtime, [run_id])
        assert runtime.snapshot()[0].state == "completed", events
        assert any(event.get("text") == "vanished" for event in events)


def test_recognition_timeout_and_disconnect_are_independent_failures(image_project):
    root = image_project
    with RuntimeCoordinator(max_workers=2) as runtime:
        timed = runtime.start("waitImage('start.png', timeout=.05, poll_interval=.01)", "fixture-one", trusted=True,
                              project_root=root, mock_config={"frame_paths": [str(root / "blank.png")]})
        disconnected = runtime.start("capture()\ncapture()", "fixture-two", trusted=True, project_root=root,
                                     mock_config={"disconnect_after": 1, "resolution": [100,80]})
        events = completed(runtime, [timed, disconnected])
        errors = {event["run_id"]: event["error_type"] for event in events if event["event"] == "error"}
        assert errors == {timed: "RecognitionTimeout", disconnected: "DeviceDisconnected"}


def test_project_and_fixture_validation_before_spawn(image_project):
    with RuntimeCoordinator() as runtime:
        with pytest.raises(ValueError):
            runtime.start("pass", "fixture-one", trusted=True, project_root=image_project,
                          mock_config={"bad": float("nan")})
        with pytest.raises(ValueError):
            runtime.start("pass", "fixture-one", trusted=True, backend="adb", project_root=image_project,
                          mock_config={})
        assert runtime.snapshot() == []


def test_late_pipe_status_cannot_revive_cancelled_process(image_project):
    marker = image_project / "started.txt"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('started')\nsleep(60)"
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start(source, "fixture-one", trusted=True, project_root=image_project)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(.005)
        assert marker.exists()
        # Deliberately leave running/line statuses queued until after stop.
        runtime.cancel(run_id, grace=.2)
        assert runtime.snapshot()[0].state == "cancelled"
        runtime.poll(limit=1)
        assert runtime.snapshot()[0].state == "cancelled"


def test_normal_main_guard_dataclass_forward_annotations_and_main_import(image_project):
    source = '''from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
import sys

@dataclass
class Payload:
    value: int
    label: ClassVar[str] = "payload"

def helper(value):
    return Payload(value)

def main():
    from __main__ import helper as imported_helper
    item = imported_helper(7)
    assert item.value == 7 and Payload.label == "payload"
    assert list(Payload.__dataclass_fields__) == ["value", "label"]
    assert list(item.__dict__) == ["value"]
    assert sys.modules["__main__"].__dict__ is globals()
    assert __package__ is None and __spec__ is None
    assert __file__.endswith("guarded.py")
    tap(item.value, 11)
    print("main-guard-ran", device.serial)

if __name__ == "__main__":
    main()
'''
    parent_main = __import__("sys").modules["__main__"]
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start(source, "fixture-one", trusted=True, project_root=image_project,
                               script_id=str(image_project / "scripts/guarded.py"))
        events = completed(runtime, [run_id])
        assert runtime.snapshot()[0].state == "completed", events
        assert any(event.get("command") == "tap" and event["arguments"] == {"x": 7, "y": 11} for event in events)
        output = "".join(event["text"] for event in events if event["event"] == "output")
        assert "main-guard-ran fixture-one" in output
    assert __import__("sys").modules["__main__"] is parent_main


def test_traceback_uses_executed_buffer_instead_of_stale_source_file(image_project):
    path = image_project / "scripts/buffer.py"
    path.write_text("raise ValueError('stale disk contents')\n", encoding="utf-8")
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start("print('current buffer')\nraise RuntimeError('executed buffer')\n",
                               "fixture-one", trusted=True, project_root=image_project, script_id=str(path))
        events = completed(runtime, [run_id])
        error = next(event for event in events if event["event"] == "error")
        assert error["source_path"] == str(path) and error["source_line"] == 2
        assert "raise RuntimeError('executed buffer')" in error["traceback"]
        assert "stale disk contents" not in error["traceback"]


def test_blocking_api_line_is_reported_before_pause_and_remains_current(image_project):
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start("x = 1\nsleep(60)\n", "fixture-one", trusted=True, project_root=image_project)
        before_pause = drain_until(runtime, lambda events, runs: any(event.get("line") == 2 for event in events))
        line_events = [event for event in before_pause if event["event"] == "line"]
        assert line_events[0]["line"] == 1 and line_events[-1]["line"] == 2
        runtime.pause(run_id)
        paused = drain_until(runtime, lambda events, runs: runs[0].state == "paused")
        assert not any(event["event"] == "line" and event["line"] != 2 for event in paused)
        time.sleep(.1)
        assert not any(event["event"] == "line" and event["line"] != 2 for event in runtime.poll())
        runtime.cancel(run_id, grace=.2)
        completed(runtime, [run_id])


def test_fast_blocking_api_loop_line_reporting_is_coalesced(image_project):
    source = "import time\nend=time.monotonic()+.3\nwhile time.monotonic()<end:\n    sleep(.001)\n"
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start(source, "fixture-one", trusted=True, project_root=image_project)
        events = completed(runtime, [run_id])
        assert runtime.snapshot()[0].state == "completed"
        lines = [event for event in events if event["event"] == "line"]
        assert len(lines) <= 8
        assert all(second["timestamp"] - first["timestamp"] >= .045 for first, second in zip(lines, lines[1:]))
