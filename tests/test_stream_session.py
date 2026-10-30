from fractions import Fraction
import hashlib
import io
import socket
import struct
import threading
import time

import av
import numpy as np
import pytest

from app.devices.adb import AdbError, ScreenInfo, png_dimensions
from app.streaming import session as module
from app.streaming.session import ScrcpySession, StreamOptions


def h264(width, height, rgb):
    encoder = av.CodecContext.create("libx264", "w")
    encoder.width, encoder.height = width, height
    encoder.pix_fmt = "yuv420p"
    encoder.time_base = Fraction(1, 30)
    encoder.options = {"preset": "ultrafast", "tune": "zerolatency"}
    frame = av.VideoFrame.from_ndarray(np.full((height, width, 3), rgb, dtype=np.uint8), format="rgb24")
    return b"".join(bytes(packet) for packet in encoder.encode(frame) + encoder.encode(None))


class FakeAdb:
    executable = "fixture-adb"

    def __init__(self, geometries=((640, 960), (960, 640))):
        self.calls = []
        self.geometries = iter(geometries)

    def _device(self, serial, *args):
        self.calls.append((serial, args))
        if args[:2] == ("forward", "tcp:0"):
            return b"31901\n"
        return b""

    def screenshot(self, serial):
        self.calls.append((serial, ("screenshot",)))
        width, height = next(self.geometries)
        return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00" + b"\x00" * 4

    def screen_info(self, serial):
        width, height = png_dimensions(self.screenshot(serial))
        return ScreenInfo(width, height, 0)


class FakeProcess:
    def __init__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.stdout = io.BytesIO(b"[server] INFO: Fixture video-only server\n")
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture
def server_file(tmp_path, monkeypatch):
    path = tmp_path / "scrcpy-server-v3.1"
    path.write_bytes(b"explicit-fixture-server-not-real-android-binary")
    monkeypatch.setattr(module, "SERVER_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def test_complete_fragmented_transport_actual_decoder_rotation_and_owned_cleanup(monkeypatch, server_file):
    first = h264(64, 96, (200, 30, 70))
    second = h264(96, 64, (20, 180, 90))
    wire = (b"\x00" + b"Fixture Android".ljust(64, b"\x00") + struct.pack(">III", 0x68323634, 64, 96)
            + struct.pack(">QI", 1 << 62, len(first)) + first
            + struct.pack(">QI", (1 << 62) | 33_333, len(second)) + second)
    client, sender = socket.socketpair()
    processes = []
    def popen(args, **kwargs):
        process = FakeProcess(args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(module.socket, "create_connection", lambda address, timeout: client)
    def send():
        try:
            for index in range(0, len(wire), 7):
                sender.sendall(wire[index:index + 7])
        finally:
            sender.close()
    producer = threading.Thread(target=send)
    producer.start()
    adb = FakeAdb()
    frames, states = [], []
    session = ScrcpySession(adb, "SERIAL-ONE", server_file, StreamOptions(max_fps=15, max_size=720, bitrate=2_000_000),
                            frames.append, lambda state, error: states.append((state, error)))
    session.run()
    producer.join(2)
    assert len(frames) == 2
    assert [(f.width, f.height, f.source_width, f.source_height) for f in frames] == [(64, 96, 640, 960), (96, 64, 960, 640)]
    assert [f.sequence for f in frames] == [1, 2]
    assert all(f.serial == "SERIAL-ONE" and isinstance(f.rgb, bytes) for f in frames)
    assert any(state == "streaming" for state, _ in states)
    assert states[-1][0] == "failed" and "StreamClosed" in states[-1][1]
    assert all(serial == "SERIAL-ONE" for serial, _ in adb.calls)
    assert ("SERIAL-ONE", ("forward", "--remove", "tcp:31901")) in adb.calls
    assert ("SERIAL-ONE", ("shell", "rm", "-f", session.remote_path)) in adb.calls
    assert processes[0].terminated
    arguments = processes[0].args
    assert arguments[:4] == ["fixture-adb", "-s", "SERIAL-ONE", "shell"]
    for required in ("3.1", "audio=false", "control=false", "video_codec=h264", "tunnel_forward=true", "max_size=720", "max_fps=15", "video_bit_rate=2000000"):
        assert required in arguments
    assert not processes[0].kwargs["shell"]


def test_wrong_server_rejected_before_any_adb_command(tmp_path):
    path = tmp_path / "wrong-server"
    path.write_bytes(b"wrong")
    adb, states = FakeAdb(), []
    ScrcpySession(adb, "PHONE", path, StreamOptions(), lambda frame: None, lambda state, error: states.append((state, error))).run()
    assert not adb.calls
    assert states[-1][0] == "failed" and "integrity/version" in states[-1][1]


def test_cancellation_before_upload_and_distinct_remote_names(server_file):
    adb, states = FakeAdb(), []
    first = ScrcpySession(adb, "PHONE", server_file, StreamOptions(), lambda frame: None, lambda state, error: states.append((state, error)))
    second = ScrcpySession(adb, "PHONE2", server_file, StreamOptions(), lambda frame: None, lambda state, error: None)
    assert first.remote_path != second.remote_path
    first.request_stop()
    first.run()
    assert not adb.calls and states[-1] == ("stopped", None)


def test_geometry_mismatch_never_publishes_an_incorrect_mapping(monkeypatch, server_file):
    client, sender = socket.socketpair()
    data = h264(64, 96, (200, 30, 70))
    sender.sendall(b"\x00" + b"Fixture".ljust(64, b"\x00") + struct.pack(">IIIQI", 0x68323634, 64, 96, 1 << 62, len(data)) + data)
    sender.close()
    monkeypatch.setattr(module.socket, "create_connection", lambda address, timeout: client)
    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    adb, frames, states = FakeAdb(((960, 640),)), [], []
    ScrcpySession(adb, "PHONE", server_file, StreamOptions(), frames.append, lambda state, error: states.append((state, error))).run()
    assert frames == []
    assert "orientation changed" in states[-1][1]


def test_cancel_idle_stream_closes_socket_and_cleans_up(monkeypatch, server_file):
    client, sender = socket.socketpair()
    sender.sendall(b"\x00" + b"Fixture".ljust(64, b"\x00") + struct.pack(">III", 0x68323634, 64, 96))
    monkeypatch.setattr(module.socket, "create_connection", lambda address, timeout: client)
    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    states = []
    session = ScrcpySession(FakeAdb(), "PHONE", server_file, StreamOptions(), lambda frame: None, lambda state, error: states.append((state, error)))
    thread = threading.Thread(target=session.run)
    thread.start()
    deadline = time.monotonic() + 2
    while session.connection is None and time.monotonic() < deadline:
        time.sleep(0.005)
    assert session.connection is not None
    session.request_stop()
    thread.join(2)
    sender.close()
    assert not thread.is_alive() and states[-1] == ("stopped", None)


def test_same_encoded_size_rechecks_original_size_and_180_degree_rotation(monkeypatch, server_file):
    client, sender = socket.socketpair()
    data = h264(64, 96, (200, 30, 70))
    packet = struct.pack(">QI", 1 << 62, len(data)) + data
    sender.sendall(b"\x00" + b"Fixture".ljust(64, b"\x00") + struct.pack(">III", 0x68323634, 64, 96) + packet + packet)
    sender.close()
    monkeypatch.setattr(module.socket, "create_connection", lambda address, timeout: client)
    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    # Force the periodic checkpoint on every frame to avoid a timing-dependent
    # sleep. The second media frame has unchanged encoder dimensions.
    monkeypatch.setattr(module, "SOURCE_GEOMETRY_CHECK_SECONDS", 0)
    adb = FakeAdb()
    observed = iter((ScreenInfo(640, 960, 0), ScreenInfo(1280, 1920, 180)))
    adb.screen_info = lambda serial: next(observed)
    frames, states = [], []
    ScrcpySession(adb, "PHONE", server_file, StreamOptions(), frames.append, lambda state, error: states.append((state, error))).run()
    assert [(frame.width, frame.height) for frame in frames] == [(64, 96), (64, 96)]
    assert [(frame.source_width, frame.source_height, frame.orientation) for frame in frames] == [(640, 960, 0), (1280, 1920, 180)]


@pytest.mark.parametrize("config_only", [False, True])
def test_header_without_first_video_frame_fails_within_startup_deadline(monkeypatch, server_file, config_only):
    client, sender = socket.socketpair()
    wire = b"\x00" + b"Fixture".ljust(64, b"\x00") + struct.pack(">III", 0x68323634, 64, 96)
    if config_only:
        wire += struct.pack(">QI", 1 << 63, 3) + b"sps"
    sender.sendall(wire)
    monkeypatch.setattr(module.socket, "create_connection", lambda address, timeout: client)
    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    real_protocol = module.ScrcpyProtocol
    monkeypatch.setattr(module, "ScrcpyProtocol", lambda *args, **kwargs: real_protocol(*args, **kwargs, read_timeout=0.05))
    states = []
    session = ScrcpySession(FakeAdb(), "PHONE", server_file, StreamOptions(), lambda frame: pytest.fail("Unexpected frame"),
                            lambda state, error: states.append((state, error)))
    started = time.monotonic()
    session.run()
    sender.close()
    assert time.monotonic() - started < 1
    assert states[-1][0] == "failed" and "Timed out" in states[-1][1]
    assert client.fileno() == -1


def test_cancellation_during_dummy_handshake_closes_owned_socket(monkeypatch, server_file):
    client, sender = socket.socketpair()
    monkeypatch.setattr(module.socket, "create_connection", lambda address, timeout: client)
    processes = []
    def popen(args, **kwargs):
        process = FakeProcess(args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    adb, states = FakeAdb(), []
    session = ScrcpySession(adb, "PHONE", server_file, StreamOptions(), lambda frame: None,
                            lambda state, error: states.append((state, error)))
    thread = threading.Thread(target=session.run)
    thread.start()
    deadline = time.monotonic() + 2
    while session.connection is None and time.monotonic() < deadline:
        time.sleep(0.005)
    assert session.connection is client
    session.request_stop()
    thread.join(2)
    sender.close()
    assert not thread.is_alive() and client.fileno() == -1
    assert processes[0].terminated
    assert states[-1] == ("stopped", None)
    assert ("PHONE", ("forward", "--remove", "tcp:31901")) in adb.calls
