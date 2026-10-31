"""Debugger acceptance exercises actual isolated spawned Python workers."""
import hashlib
import time

import pytest

from app.automation.debugger import command_bytes, safe_value, validate_breakpoints, variables
from app.automation.runtime import RuntimeCoordinator


def until(runtime, predicate, timeout=10):
    events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events.extend(runtime.poll())
        if predicate(events):
            return events
        time.sleep(.005)
    pytest.fail(f"Debugger timed out: {runtime.snapshot()}, events={events[-5:]}")


def stopped(runtime):
    events = until(runtime, lambda events: any(event["event"] == "debug_stopped" for event in events))
    # Consume acknowledgment if a stop and its ack arrived in different ticks.
    return next(event for event in reversed(events) if event["event"] == "debug_stopped")


def command(runtime, run, action, **payload):
    # Acknowledge the preceding command, independent of the GUI's event timing.
    until(runtime, lambda events: not runtime._runs[run].debug_pending)
    runtime.debug_command(run, action, **payload)


def finished(runtime, run):
    return until(runtime, lambda events: any(info.run_id == run and info.exitcode is not None
                                            for info in runtime.snapshot()))


def test_inspection_never_calls_custom_metaclass_name_descriptor():
    class Meta(type):
        @property
        def __name__(cls):
            raise AssertionError("Inspector executed a user descriptor")

    class Value(metaclass=Meta):
        pass

    value = Value()
    assert safe_value(value) == "<Value object>"
    assert variables({"target": value}) == [{"name": "target", "type": "Value", "value": "<Value object>"}]


def test_breakpoint_snapshot_variables_steps_and_normal_finish(tmp_path):
    source = "def add(n):\n    inside = n + 2\n    return inside\nx = 3\ny = add(x)\nprint(y)\n"
    with RuntimeCoordinator() as runtime:
        run = runtime.start(source, "fixture-debug", trusted=True, project_root=tmp_path,
                            debug=True, breakpoints=[5])
        event = stopped(runtime)
        assert event["line"] == 5 and event["reason"] == "breakpoint"
        assert event["source_hash"] == hashlib.sha256(source.encode()).hexdigest()
        assert {item["name"]: item["value"] for item in event["locals"]}["x"] == "3"
        command(runtime, run, "step_into")
        event = stopped(runtime)
        assert event["line"] == 2 and event["stack"][0]["name"] == "add"
        assert {item["name"]: item["value"] for item in event["locals"]}["n"] == "3"
        command(runtime, run, "step_over")
        assert stopped(runtime)["line"] == 3
        command(runtime, run, "step_out")
        event = stopped(runtime)
        # bdb reports the callee's return boundary before caller continuation.
        assert event["reason"] in {"return", "step"}
        command(runtime, run, "continue")
        finished(runtime, run)
        assert runtime.snapshot()[0].state == "completed"


def test_debug_paused_device_does_not_freeze_another_worker_and_stop(tmp_path):
    with RuntimeCoordinator(max_workers=2) as runtime:
        paused = runtime.start("value = 12\ntap(value, 2)\n", "fixture-debug", trusted=True,
                               project_root=tmp_path, debug=True, breakpoints=[2])
        stopped(runtime)
        other = runtime.start("tap(8, 9)\nprint('independent')", "fixture-other", trusted=True,
                              project_root=tmp_path)
        events = finished(runtime, other)
        assert any(event.get("command") == "tap" and event["serial"] == "fixture-other" for event in events)
        assert next(info for info in runtime.snapshot() if info.run_id == paused).state == "paused"
        runtime.cancel(paused, grace=.2)
        finished(runtime, paused)
        assert next(info for info in runtime.snapshot() if info.run_id == paused).state == "cancelled"


def test_pause_busy_debug_worker_dynamic_breakpoints_and_source_is_frozen(tmp_path):
    path = tmp_path / "loop.py"
    source = "count = 0\nwhile count < 100000000:\n    count += 1\nprint(count)\n"
    path.write_text(source)
    with RuntimeCoordinator() as runtime:
        run = runtime.start(source, "fixture-debug", trusted=True, script_id=str(path),
                            project_root=tmp_path, debug=True)
        until(runtime, lambda events: any(event.get("state") == "running" for event in events))
        command(runtime, run, "pause")
        event = stopped(runtime)
        assert event["line"] in (1, 2, 3)
        path.write_text("raise Exception('edited disk')\n")
        command(runtime, run, "set_breakpoints", lines=[3])
        until(runtime, lambda events: any(event["event"] == "debug_ack" for event in events))
        command(runtime, run, "continue")
        assert stopped(runtime)["line"] == 3
        runtime.cancel(run, grace=.2)


def test_inspection_never_calls_user_repr(tmp_path):
    marker = tmp_path / "repr-called"
    source = ("class Hostile:\n    def __repr__(self):\n"
              f"        open({str(marker)!r}, 'w').write('bad')\n        return 'bad'\n"
              "value = Hostile()\nnext_line = 2\n")
    with RuntimeCoordinator() as runtime:
        run = runtime.start(source, "fixture-debug", trusted=True, project_root=tmp_path,
                            debug=True, breakpoints=[6])
        event = stopped(runtime)
        assert {item["name"]: item["value"] for item in event["locals"]}["value"] == "<Hostile object>"
        assert not marker.exists()
        runtime.cancel(run, grace=.2)


def test_debug_protocol_rejects_eval_and_invalid_breakpoints(tmp_path):
    assert safe_value(10 ** 10000) == "<large integer>"
    with pytest.raises(ValueError):
        command_bytes("eval", {"expression": "dangerous()"})
    with pytest.raises(ValueError):
        validate_breakpoints([True], "pass")
    with RuntimeCoordinator() as runtime:
        with pytest.raises(ValueError):
            runtime.start("pass", "fixture-debug", trusted=True, project_root=tmp_path,
                          debug=True, breakpoints=[2])
        assert runtime.snapshot() == []


def test_debug_stdlib_imports_handled_exceptions_and_frame_selection(tmp_path):
    source = ("import pathlib, json\nouter = 7\ndef helper():\n"
              "    try:\n        raise ValueError('handled')\n"
              "    except ValueError:\n        local = json.loads('12')\n"
              "    return local\nresult = helper()\nprint(result)\n")
    with RuntimeCoordinator() as runtime:
        run = runtime.start(source, "fixture-debug", trusted=True, project_root=tmp_path,
                            debug=True, breakpoints=[5])
        assert stopped(runtime)["line"] == 5
        command(runtime, run, "inspect", frame_index=1)
        event = stopped(runtime)
        assert event["selected_frame"] == 1
        assert {item["name"]: item["value"] for item in event["locals"]}["outer"] == "7"
        command(runtime, run, "step_over")
        event = stopped(runtime)
        assert event["reason"] == "exception" and event["exception"]["type"] == "ValueError"
        command(runtime, run, "continue")
        finished(runtime, run)
        assert runtime.snapshot()[0].state == "completed"


def test_large_unicode_variable_preview_stays_within_json_ipc_budget(tmp_path):
    source = "payload = {str(i): '📱' * 200 for i in range(60)}\nprint('ready')\n"
    with RuntimeCoordinator() as runtime:
        run = runtime.start(source, "fixture-debug", trusted=True, project_root=tmp_path,
                            debug=True, breakpoints=[2])
        event = stopped(runtime)
        import json
        assert len(json.dumps(event, ensure_ascii=True).encode()) < 64 * 1024
        assert event["locals"][0]["name"] == "payload"
        runtime.cancel(run, grace=.2)


def test_debug_pause_during_cancellable_api_wait(tmp_path):
    with RuntimeCoordinator() as runtime:
        run = runtime.start("value = 3\nsleep(60)\n", "fixture-debug", trusted=True,
                            project_root=tmp_path, debug=True)
        until(runtime, lambda events: any(event.get("event") == "line" and event.get("line") == 2 for event in events))
        command(runtime, run, "pause")
        event = stopped(runtime)
        assert event["line"] == 2 and event["reason"] == "pause"
        runtime.cancel(run, grace=.2)
