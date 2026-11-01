"""Bounded actual Device reads; no generic action replay callbacks."""
from dataclasses import replace
import time

import cv2
import numpy as np
import pytest

from app.automation.api import Device, errors
from app.automation.recovery import (RecoveryBudgetExceeded, RecoveryCheckpoint, RecoveryEngine,
                                     RecoverySession, RetryPolicy)
from app.automation.runtime import RuntimeCoordinator
from app.projects.library import AssetLibrary
from app.simulation.model import SimulationManager
from app.simulation.project import create_project
from test_script_runtime import completed


class ReadBackend:
    serial = "recovery-fixture"

    def __init__(self, failures=()):
        self.failures = list(failures)
        self.reads = 0
        self.actions = 0

    def capture(self):
        self.reads += 1
        if self.failures:
            error = self.failures.pop(0)
            if error is not None:
                raise error
        return np.zeros((40, 80, 3), dtype=np.uint8)

    def tap(self, x, y):
        self.actions += 1


def make_device(tmp_path, *, failures=(), wait=None, checkpoint=None):
    backend = ReadBackend(failures)
    device = Device(backend, AssetLibrary(tmp_path), checkpoint=checkpoint, interruptible_wait=wait)
    return device, backend


@pytest.mark.parametrize("change", [
    {"max_attempts": True}, {"max_attempts": 0}, {"max_attempts": 11},
    {"initial_delay": -1}, {"initial_delay": float("nan")},
    {"max_delay": 61}, {"max_delay": 10**400},
    {"multiplier": float("inf")}, {"multiplier": 0}, {"multiplier": True},
    {"budget": 0}, {"budget": 86401}, {"budget": float("nan")},
])
def test_invalid_policy_rejected_before_device_use(change):
    with pytest.raises(ValueError):
        RetryPolicy(**change)


def test_explicit_retries_of_read_only_failure_and_bounded_backoff(tmp_path):
    waits = []
    events = []
    device, backend = make_device(tmp_path, failures=[errors.FrameUnavailable("one"), errors.FrameUnavailable("two")],
                                  wait=waits.append)
    engine = RecoveryEngine(device, RetryPolicy(max_attempts=3, initial_delay=.02, multiplier=3, max_delay=.04), on_event=events.append)
    assert engine.read("capture").resolution == (80, 40)
    assert backend.reads == 3 and backend.actions == 0
    assert waits == [.02, .04]
    assert [event["attempt"] for event in events] == [1, 2]
    assert all(event["serial"] == backend.serial for event in events)


def test_default_policy_never_retries(tmp_path):
    device, backend = make_device(tmp_path, failures=[errors.FrameUnavailable("absent")])
    with pytest.raises(errors.FrameUnavailable):
        RecoveryEngine(device).read("capture")
    assert backend.reads == 1


@pytest.mark.parametrize("method", ["click", "tap", "doubleClick", "swipe", "home", "back", "launchApp", "typeText", lambda: None])
def test_input_and_arbitrary_callbacks_cannot_enter_recovery(method, tmp_path):
    device, backend = make_device(tmp_path)
    with pytest.raises(ValueError, match="read-only"):
        RecoveryEngine(device, RetryPolicy(max_attempts=3)).read(method, 1, 2)
    assert backend.reads == 0 and backend.actions == 0


@pytest.mark.parametrize("error", [
    errors.CommandTimeout("possibly sent"), errors.CommandFailed("unknown"),
    errors.DeviceDisconnected("lost"), errors.DeviceOffline("offline"),
    errors.DeviceUnauthorized("unauthorized"), errors.AssetNotFound("missing"),
    errors.InvalidAsset("bad"), errors.AmbiguousMatch("two"),
    errors.OCRUnavailable("not installed"), errors.Cancelled("stop"),
    ValueError("ImageNotFound"),
])
def test_unsafe_or_persistent_faults_never_retry_even_with_policy(error, tmp_path):
    device, backend = make_device(tmp_path, failures=[error])
    with pytest.raises(type(error)):
        RecoveryEngine(device, RetryPolicy(max_attempts=10, initial_delay=0)).read("capture")
    assert backend.reads == 1 and backend.actions == 0


def test_cancellation_during_backoff_stops_before_next_read(tmp_path):
    def cancel_wait(seconds):
        raise errors.Cancelled("Emergency stop during recovery")
    device, backend = make_device(tmp_path, failures=[errors.FrameUnavailable("temporary")], wait=cancel_wait)
    with pytest.raises(errors.Cancelled):
        RecoveryEngine(device, RetryPolicy(max_attempts=10)).read("capture")
    assert backend.reads == 1 and backend.actions == 0


def test_total_budget_exhausts_before_sleep_or_retry(tmp_path):
    waits = []
    device, backend = make_device(tmp_path, failures=[errors.FrameUnavailable("not ready")], wait=waits.append)
    with pytest.raises(RecoveryBudgetExceeded):
        RecoveryEngine(device, RetryPolicy(max_attempts=3, initial_delay=1, budget=.1)).read("capture")
    assert backend.reads == 1 and not waits


def test_budget_accounts_for_time_inside_the_read(tmp_path, monkeypatch):
    device, backend = make_device(tmp_path)
    original = backend.capture
    def delayed():
        time.sleep(.03)
        return original()
    monkeypatch.setattr(backend, "capture", delayed)
    with pytest.raises(RecoveryBudgetExceeded):
        RecoveryEngine(device, RetryPolicy(max_attempts=3, budget=.005)).read("capture")
    assert backend.reads == 1


@pytest.mark.parametrize("clock", [0.0, 1024.0, 1_000_000_000.0])
def test_wait_timeout_is_clamped_including_positional_arguments(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(time, "monotonic", lambda: clock)
    observed = []
    def waitImage(self, image, timeout=10, *, poll_interval=.2):
        observed.append(timeout)
        return "found"
    monkeypatch.setattr(Device, "waitImage", waitImage)
    device, _ = make_device(tmp_path)
    engine = RecoveryEngine(device, RetryPolicy(budget=.2))
    assert engine.read("waitImage", "image.png", 999) == "found"
    assert 0 < observed[-1] <= .2
    assert engine.read("waitImage", "image.png") == "found"
    assert 0 < observed[-1] <= .2


def test_session_and_checkpoint_cannot_resume_another_source_or_generation(tmp_path):
    device, backend = make_device(tmp_path)
    session = RecoverySession.for_source(backend.serial, 1, "print('approved')")
    current = [session]
    engine = RecoveryEngine(device, RetryPolicy(max_attempts=2), session=session, current_session=lambda: current[0])
    checkpoint = engine.checkpoint("screen inspected", {"stage": 2})
    assert engine.verify_checkpoint(checkpoint) == {"stage": 2}
    current[0] = replace(session, generation=2)
    with pytest.raises(errors.DeviceDisconnected):
        engine.read("capture")
    with pytest.raises(errors.DeviceDisconnected):
        engine.verify_checkpoint(checkpoint)
    assert backend.reads == 0
    current[0] = session
    alien = RecoveryCheckpoint(replace(session, source_hash="0"*64), "other source", "null")
    with pytest.raises(errors.DeviceDisconnected):
        engine.verify_checkpoint(alien)


def test_obsolete_generation_during_backoff_is_not_retried(tmp_path):
    device, backend = make_device(tmp_path, failures=[errors.FrameUnavailable("temporary")])
    session = RecoverySession.for_source(backend.serial, 1, "pass")
    current = [session]
    device._interruptible_wait = lambda seconds: current.__setitem__(0, replace(session, generation=2))
    with pytest.raises(errors.DeviceDisconnected):
        RecoveryEngine(device, RetryPolicy(max_attempts=2), session=session, current_session=lambda: current[0]).read("capture")
    assert backend.reads == 1


def test_checkpoint_is_bounded_finite_data_and_never_executes(tmp_path):
    device, backend = make_device(tmp_path)
    session = RecoverySession.for_source(backend.serial, 1, "pass")
    with pytest.raises(ValueError):
        RecoveryEngine(device, session=session)
    engine = RecoveryEngine(device, session=session, current_session=lambda: session)
    for bad in ({"value": float("nan")}, {"value": "x"*17000}, object()):
        with pytest.raises(ValueError):
            engine.checkpoint("marker", bad)
    checkpoint = engine.checkpoint("inert text", "__import__('os').system('anything')")
    assert "__import__" in engine.verify_checkpoint(checkpoint)
    assert backend.reads == 0 and backend.actions == 0


def test_real_simulator_delayed_target_recovers_in_spawned_worker_without_input(tmp_path):
    manager = SimulationManager()
    try:
        info = manager.create("wait", delay=2)
        root, _ = create_project(tmp_path, info.serial, "wait")
        source = ("from app.automation.recovery import RecoveryEngine, RetryPolicy\n"
                  "engine=RecoveryEngine(device, RetryPolicy(max_attempts=10,initial_delay=.1,max_delay=.4,budget=5),on_event=lambda e: print(e['event']))\n"
                  "target=engine.read('find','reward.png')\n"
                  "assert target.device_serial == device.serial\nprint('recovered-without-input')\n")
        with RuntimeCoordinator() as runtime:
            run = runtime.start(source, info.serial, backend="simulation", simulation_config=manager.config(info.serial),
                                trusted=True, project_root=root)
            events = completed(runtime, [run])
            assert runtime.snapshot()[0].state == "completed", events
            output = "".join(e["text"] for e in events if e["event"] == "output")
            assert "recovered-without-input" in output and "recovery_retry" in output
            assert manager.client(info.serial).state()["actions"] == 0
    finally:
        manager.close()
