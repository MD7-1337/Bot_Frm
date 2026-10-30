"""Real spawn/IPC tests using declared mock-device fixtures, never real phones."""

import time

import pytest

from app.automation.runtime import DeviceBusyError, RuntimeCoordinator, TrustRequiredError, WorkerLimitError


def collect_finished(runtime, run_ids, timeout=8):
    events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events.extend(runtime.poll())
        completed = {run.run_id for run in runtime.snapshot()
                     if run.state in {"completed", "failed", "cancelled"} and run.exitcode is not None}
        if set(run_ids) <= completed:
            events.extend(runtime.poll())
            return events
        time.sleep(0.01)
    pytest.fail(f"Workers did not finish: {runtime.snapshot()}")


def test_spawned_workers_keep_independent_assignments():
    source = "assert getDevice() == expected\ntap(x, 20)\nsleep(0.05)\nhome()"
    with RuntimeCoordinator(max_workers=2) as runtime:
        one = runtime.start("expected='fixture-one'\nx=11\n" + source, "fixture-one", trusted=True)
        two = runtime.start("expected='fixture-two'\nx=22\n" + source, "fixture-two", trusted=True)
        events = collect_finished(runtime, [one, two])
        taps = [e for e in events if e["event"] == "action" and e["command"] == "tap"]
        assert {(e["serial"], e["arguments"]["x"]) for e in taps} == {("fixture-one", 11), ("fixture-two", 22)}
        assert all(e["backend"] == "mock" for e in events)
        assert len({run.pid for run in runtime.snapshot()}) == 2
        assert all(run.state == "completed" for run in runtime.snapshot())


def test_failure_does_not_stop_another_device():
    with RuntimeCoordinator() as runtime:
        failing = runtime.start("raise RuntimeError('expected fixture failure')", "fixture-one", trusted=True)
        succeeding = runtime.start("sleep(0.1)\ntap(4, 5)", "fixture-two", trusted=True)
        events = collect_finished(runtime, [failing, succeeding])
        states = {run.run_id: run.state for run in runtime.snapshot()}
        assert states == {failing: "failed", succeeding: "completed"}
        assert any(e["event"] == "error" and e["error_type"] == "RuntimeError" for e in events)
        assert any(e["event"] == "action" and e["run_id"] == succeeding for e in events)


def test_explicit_trust_required_even_for_mock():
    with RuntimeCoordinator() as runtime:
        with pytest.raises(TrustRequiredError):
            runtime.start("tap(1,2)", "fixture-one")
        assert runtime.snapshot() == []


def test_device_lease_worker_limit_and_release():
    with RuntimeCoordinator(max_workers=1) as runtime:
        first = runtime.start("sleep(10)", "fixture-one", trusted=True)
        with pytest.raises(DeviceBusyError):
            runtime.start("pass", "fixture-one", trusted=True)
        with pytest.raises(WorkerLimitError):
            runtime.start("pass", "fixture-two", trusted=True)
        runtime.cancel(first)
        collect_finished(runtime, [first])
        second = runtime.start("tap(3, 4)", "fixture-one", trusted=True)
        collect_finished(runtime, [second])
        assert runtime.snapshot()[-1].state == "completed"


@pytest.mark.parametrize("source", ["sleep(60)", "while True: pass"])
def test_bounded_cancellation_cooperative_and_forced(source):
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start(source, "fixture-one", trusted=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if any(e.get("state") == "running" for e in runtime.poll()):
                break
            time.sleep(0.01)
        else:
            pytest.fail("Worker never entered running state")
        started = time.monotonic()
        runtime.cancel(run_id, grace=0.15)
        assert time.monotonic() - started < 3
        assert runtime.snapshot()[0].state == "cancelled"
        assert runtime.snapshot()[0].exitcode is not None


@pytest.mark.parametrize("source", ["tap(-1, 2)", "tap(True,2)", "sleep(float('nan'))", "swipe(1,2,3,4,duration=0)"])
def test_api_rejects_invalid_commands(source):
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start(source, "fixture-one", trusted=True)
        events = collect_finished(runtime, [run_id])
        assert runtime.snapshot()[0].state == "failed"
        assert not any(e["event"] == "action" for e in events)


def test_source_validation_before_spawn_and_cleanup():
    runtime = RuntimeCoordinator()
    with pytest.raises(SyntaxError):
        runtime.start("if:", "fixture-one", trusted=True)
    with pytest.raises(ValueError):
        runtime.start("pass", "", trusted=True)
    with pytest.raises(ValueError, match="1 MiB"):
        runtime.start(" " * (1024 * 1024 + 1), "fixture-one", trusted=True)
    runtime.close()
    runtime.close()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.start("pass", "fixture-one", trusted=True)
    assert runtime.snapshot() == []


def test_output_is_json_and_bounded():
    with RuntimeCoordinator() as runtime:
        run_id = runtime.start("print('x' * 20000)", "fixture-one", trusted=True)
        events = collect_finished(runtime, [run_id])
        outputs = [event["text"] for event in events if event["event"] == "output"]
        assert "".join(outputs) == "x" * 20000 + "\n"
        assert max(map(len, outputs)) <= 2048
