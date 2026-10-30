import threading
import time

import pytest

from app.streaming import manager
from app.streaming.manager import StreamManager
from app.streaming.session import StreamError, StreamOptions, VideoFrame


def spin(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("Timed out waiting for stream fixture")


class FixtureSession:
    instances = {}

    def __init__(self, adb, serial, server, options, on_frame, on_state):
        self.serial, self.options = serial, options
        self.on_frame, self.on_state = on_frame, on_state
        self.stop = threading.Event()
        self.finish = threading.Event()
        self.instances[serial] = self

    def run(self):
        self.on_state("starting", None)
        self.on_frame(VideoFrame(self.serial, b"\x00" * 18, 2, 3, 200, 300, time.monotonic(), 1))
        self.on_state("streaming", None)
        self.stop.wait(3)
        self.finish.wait(3)
        self.on_state("stopped", None)

    def request_stop(self):
        self.stop.set()


@pytest.fixture
def fixture_manager(monkeypatch):
    FixtureSession.instances = {}
    monkeypatch.setattr(manager, "ScrcpySession", FixtureSession)
    streams = StreamManager(max_sessions=2)
    yield streams
    for session in FixtureSession.instances.values():
        session.finish.set()
    assert streams.close(2)


def test_independent_sources_latest_only_stop_and_restart(fixture_manager):
    streams = fixture_manager
    streams.start("phone-A", StreamOptions(max_fps=15, bitrate=2_000_000, max_size=720))
    streams.start("phone-B")
    spin(lambda: streams.latest("phone-A") is not None and streams.latest("phone-B") is not None)
    assert streams.latest("phone-A").serial == "phone-A"
    assert streams.latest("phone-B").serial == "phone-B"
    first = FixtureSession.instances["phone-A"]
    assert first.options.max_fps == 15
    for sequence in range(2, 100):
        first.on_frame(VideoFrame("phone-A", b"\x00" * 18, 2, 3, 200, 300, time.monotonic(), sequence))
    assert streams.latest("phone-A").sequence == 99
    assert streams.status("phone-A").frames == 99
    streams.stop("phone-A")
    assert streams.latest("phone-A") is None and streams.status("phone-A").state == "stopping"
    first.on_frame(VideoFrame("phone-A", b"\x00" * 18, 2, 3, 200, 300, time.monotonic(), 100))
    assert streams.latest("phone-A") is None
    assert streams.latest("phone-B") is not None
    with pytest.raises(StreamError, match="stopping"):
        streams.start("phone-A")
    first.finish.set()
    spin(lambda: streams.status("phone-A").state == "stopped")
    streams.start("phone-A")
    spin(lambda: streams.latest("phone-A") is not None)


def test_limit_error_isolation_and_nonblocking_close(fixture_manager):
    streams = fixture_manager
    streams.start("phone-A")
    streams.start("phone-B")
    spin(lambda: streams.status("phone-A").state == "streaming")
    with pytest.raises(StreamError, match="Maximum"):
        streams.start("phone-C")
    first = FixtureSession.instances["phone-A"]
    first.on_state("failed", "Fixture disconnect")
    assert streams.status("phone-A").error == "Fixture disconnect"
    assert streams.latest("phone-A") is None
    assert streams.latest("phone-B") is not None
    start = time.monotonic()
    assert not streams.close(timeout=0)
    assert time.monotonic() - start < 0.1
    with pytest.raises(StreamError, match="closed"):
        streams.start("phone-C")


@pytest.mark.parametrize("kwargs", [{"max_fps": 0}, {"max_fps": True}, {"max_fps": float("nan")},
                                    {"bitrate": 1}, {"max_size": 0}, {"max_size": 10000}])
def test_video_settings_validation(kwargs):
    with pytest.raises(ValueError):
        StreamOptions(**kwargs)


def test_unknown_stop_and_validation():
    streams = StreamManager()
    assert streams.latest("unknown") is None
    assert streams.status("unknown").state == "stopped"
    streams.stop("unknown")
    with pytest.raises(ValueError):
        streams.close(float("nan"))
    assert streams.close()
