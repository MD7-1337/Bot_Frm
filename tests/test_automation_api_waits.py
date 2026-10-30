"""Deterministic monotonic waits exercise actual matching without timing flakes."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.automation.api import (
    AmbiguousMatch, AssetNotFound, Cancelled, Device, DeviceDisconnected,
    Match, Pattern, RecognitionTimeout,
)
from app.projects.library import AssetLibrary


class Frames:
    serial = "fixture-wait-phone"

    def __init__(self, frames):
        self.frames = frames
        self.count = 0
        self.before_capture = lambda: None

    def capture(self):
        self.before_capture()
        frame = self.frames[min(self.count, len(self.frames) - 1)]
        self.count += 1
        return frame.copy()


@pytest.fixture
def timed(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    rng = np.random.default_rng(181)
    template = rng.integers(40, 220, (7, 6, 3), dtype=np.uint8)
    blank = np.zeros((35, 40, 3), np.uint8)
    present = blank.copy()
    present[10:17, 20:26] = template
    success, encoded = cv2.imencode(".png", cv2.cvtColor(template, cv2.COLOR_RGB2BGR))
    assert success
    (tmp_path / "images/start.png").write_bytes(encoded.tobytes())
    clock = [0.0]
    waits = []
    monkeypatch.setattr("app.automation.api.device.time.monotonic", lambda: clock[0])
    def delay(seconds):
        waits.append(seconds)
        clock[0] += seconds
    def make(frames, checkpoint=None):
        backend = Frames(frames)
        return Device(backend, AssetLibrary(tmp_path), checkpoint=checkpoint, interruptible_wait=delay), backend
    return make, clock, waits, blank, present


def test_appearance_wait_uses_actual_frame_sequence(timed):
    make, clock, waits, blank, present = timed
    device, backend = make([blank, blank, present])
    found = device.waitImage(Pattern("start.png").similar(.99), timeout=2, poll_interval=.25)
    assert isinstance(found, Match) and found.region.x == 20 and found.region.y == 10
    assert backend.count == 3 and waits == [.25, .25] and clock[0] == .5


def test_vanish_requires_valid_negative_frame(timed):
    make, _, waits, blank, present = timed
    device, backend = make([present, present, blank])
    assert device.waitVanish("start.png", timeout=1, poll_interval=.1) is None
    assert backend.count == 3 and waits == [.1, .1]


def test_wait_overload_is_unambiguous(timed):
    make, clock, waits, blank, present = timed
    device, _ = make([present])
    assert device.wait(2) is None and clock[0] == 2
    assert isinstance(device.wait("start.png", timeout=0), Match)
    assert isinstance(device.wait("start.png"), Match)
    with pytest.raises(TypeError):
        device.wait(2, timeout=4)
    with pytest.raises(TypeError):
        device.wait(True)
    assert waits == [2]


@pytest.mark.parametrize("method,present_first", [("waitImage", False), ("waitVanish", True)])
def test_zero_timeout_performs_exactly_one_attempt(timed, method, present_first):
    make, _, waits, blank, present = timed
    device, backend = make([present if present_first else blank])
    with pytest.raises(RecognitionTimeout):
        getattr(device, method)("start.png", timeout=0)
    assert backend.count == 1 and waits == []
    success, backend = make([blank if present_first else present])
    result = getattr(success, method)("start.png", timeout=0)
    assert (result is None) if present_first else isinstance(result, Match)
    assert backend.count == 1


@pytest.mark.parametrize("method", ["waitImage", "waitVanish"])
def test_positive_deadline_bounds_polling_including_capture_time(timed, method):
    make, clock, waits, blank, present = timed
    fail_frame = blank if method == "waitImage" else present
    device, backend = make([fail_frame])
    with pytest.raises(RecognitionTimeout):
        getattr(device, method)("start.png", timeout=.3, poll_interval=.2)
    assert clock[0] == .3 and backend.count == 2
    assert waits == [.2, pytest.approx(.1)]


@pytest.mark.parametrize("method", ["waitImage", "waitVanish"])
def test_late_result_after_slow_capture_is_timeout(timed, method):
    make, clock, _, blank, present = timed
    device, backend = make([present if method == "waitImage" else blank])
    backend.before_capture = lambda: clock.__setitem__(0, clock[0] + 2)
    with pytest.raises(RecognitionTimeout):
        getattr(device, method)("start.png", timeout=1)
    assert backend.count == 1


def test_time_spent_paused_counts_toward_positive_deadline(timed):
    make, clock, _, blank, present = timed
    def checkpoint():
        clock[0] = 2
    device, backend = make([present], checkpoint)
    with pytest.raises(RecognitionTimeout):
        device.waitImage("start.png", timeout=1)
    assert backend.count == 0


def test_cancellation_propagates_without_more_capture_or_action(timed):
    make, _, _, blank, _ = timed
    device, backend = make([blank])
    def delay(seconds):
        raise Cancelled("fixture stop")
    device._interruptible_wait = delay
    with pytest.raises(Cancelled):
        device.waitImage("start.png", timeout=10)
    assert backend.count == 1
    def checkpoint():
        raise Cancelled("fixture checkpoint")
    device._checkpoint = checkpoint
    with pytest.raises(Cancelled):
        device.waitVanish("start.png", timeout=1)
    assert backend.count == 1


def test_errors_do_not_become_a_wait_timeout_or_vanish_success(timed):
    make, _, waits, blank, present = timed
    device, backend = make([blank])
    with pytest.raises(AssetNotFound):
        device.waitImage("missing.png", timeout=5)
    assert backend.count == 0 and waits == []
    def disconnected():
        raise DeviceDisconnected("fixture transport lost")
    backend.before_capture = disconnected
    with pytest.raises(DeviceDisconnected):
        device.waitVanish("start.png", timeout=5)
    assert backend.count == 0


def test_ambiguous_appearance_is_not_a_hidden_retry(timed):
    make, _, waits, _, present = timed
    frame = present.copy()
    frame[23:30, 4:10] = frame[10:17, 20:26]
    device, backend = make([frame])
    with pytest.raises(AmbiguousMatch):
        device.waitImage("start.png", timeout=5)
    assert backend.count == 1 and waits == []


@pytest.mark.parametrize("arguments", [{"timeout": -1}, {"timeout": float("nan")},
                                        {"timeout": True}, {"poll_interval": 0},
                                        {"poll_interval": float("inf")}])
def test_wait_arguments_fail_before_transport(timed, arguments):
    make, _, _, blank, _ = timed
    device, backend = make([blank])
    with pytest.raises(ValueError):
        device.waitImage("start.png", **arguments)
    assert backend.count == 0
