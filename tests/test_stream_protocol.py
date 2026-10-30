"""Pinned wire-format fixtures, not evidence of a connected Android device."""
import socket
import struct
import threading

import pytest

from app.streaming.protocol import (
    H264_CODEC_ID, MAX_PACKET_BYTES, PACKET_FLAG_CONFIG, PACKET_FLAG_KEY_FRAME,
    ProtocolError, ScrcpyProtocol, StreamCancelled, StreamClosed,
    VideoHeader, VideoPacket, validate_dimensions,
)


class Fragments:
    def __init__(self, data: bytes, fragment=1):
        self.data = data
        self.fragment = fragment
        self.calls = 0

    def recv(self, length):
        self.calls += 1
        chunk = self.data[:min(length, self.fragment)]
        self.data = self.data[len(chunk):]
        return chunk


def header(name="Téléphone 📱", width=1080, height=2400, codec=H264_CODEC_ID):
    encoded = name.encode("utf-8")
    return b"\0" + encoded + b"\0" * (64 - len(encoded)) + struct.pack(">III", codec, width, height)


def reader(data, *, fragment=1, **options):
    return ScrcpyProtocol(Fragments(data, fragment), threading.Event(), **options)


@pytest.mark.parametrize("fragment", [1, 2, 5, 64, 4096])
def test_fragmented_startup_and_packets(fragment):
    stream = header() + struct.pack(">QI", PACKET_FLAG_CONFIG, 3) + b"sps"
    stream += struct.pack(">QI", PACKET_FLAG_KEY_FRAME | 123_456, 5) + b"frame"
    protocol = reader(stream, fragment=fragment)
    assert protocol.read_header() == VideoHeader("Téléphone 📱", "h264", 1080, 2400)
    assert protocol.read_packet() == VideoPacket(b"sps", None, True, False)
    assert protocol.read_packet() == VideoPacket(b"frame", 123_456, False, True)
    with pytest.raises(StreamClosed):
        protocol.read_packet()


def test_regular_frame_pts_uses_62_low_bits():
    protocol = reader(header() + struct.pack(">QI", (1 << 62) - 1, 1) + b"x")
    protocol.read_header()
    assert protocol.read_packet().pts_us == (1 << 62) - 1


def test_session_can_consume_dummy_before_protocol_startup():
    protocol = reader(header()[1:] + struct.pack(">QI", 7, 1) + b"x", expect_dummy=False)
    assert protocol.read_header().device_name == "Téléphone 📱"
    assert protocol.read_packet() == VideoPacket(b"x", 7)


@pytest.mark.parametrize("codec", [0, 1, 0x68323635, 0x617631])
def test_unsupported_codec_or_disabled_without_waiting_for_size(codec):
    protocol = reader(header()[:65] + struct.pack(">I", codec))
    with pytest.raises(ProtocolError, match="[Dd]evice|[Uu]nsupported"):
        protocol.read_header()


@pytest.mark.parametrize("dimensions", [(0, 20), (20, 0), (20_000, 1), (8192, 8192)])
def test_bad_metadata_dimensions(dimensions):
    with pytest.raises(ProtocolError, match="dimensions"):
        reader(header(width=dimensions[0], height=dimensions[1])).read_header()


@pytest.mark.parametrize("dimensions", [(-1, 1), (True, 20), (1.5, 20)])
def test_direct_dimension_validation(dimensions):
    with pytest.raises(ProtocolError):
        validate_dimensions(*dimensions)


@pytest.mark.parametrize("length", [0, MAX_PACKET_BYTES + 1, 0xffffffff])
def test_bad_packet_size_rejected_before_payload_read(length):
    protocol = reader(header() + struct.pack(">QI", 1, length))
    protocol.read_header()
    with pytest.raises(ProtocolError, match="size"):
        protocol.read_packet()


def test_configured_packet_limit():
    protocol = reader(header() + struct.pack(">QI", 1, 17), max_packet_bytes=16)
    protocol.read_header()
    with pytest.raises(ProtocolError):
        protocol.read_packet()


@pytest.mark.parametrize("data", [b"", header()[:20], header()[:-1]])
def test_disconnect_during_metadata(data):
    with pytest.raises(StreamClosed):
        reader(data).read_header()


@pytest.mark.parametrize("tail", [b"\0" * 5, struct.pack(">QI", 1, 10) + b"tiny"])
def test_disconnect_during_frame(tail):
    protocol = reader(header() + tail)
    protocol.read_header()
    with pytest.raises(StreamClosed):
        protocol.read_packet()


def test_bad_dummy_byte_and_device_names():
    with pytest.raises(ProtocolError, match="connection byte"):
        reader(b"x" + header()[1:]).read_header()
    with pytest.raises(ProtocolError, match="terminator"):
        reader(b"\0" + b"x" * 64).read_header()
    with pytest.raises(ProtocolError, match="UTF-8"):
        reader(b"\0\xff" + b"\0" * 63).read_header()


def test_header_required_and_only_read_once():
    protocol = reader(header())
    with pytest.raises(ProtocolError, match="metadata"):
        protocol.read_packet()
    protocol.read_header()
    with pytest.raises(ProtocolError, match="already"):
        protocol.read_header()


def test_cancel_before_read_and_while_idle():
    stop = threading.Event()
    stop.set()
    protocol = ScrcpyProtocol(Fragments(header()), stop)
    with pytest.raises(StreamCancelled):
        protocol.read_header()
    stop.clear()

    class Idle(Fragments):
        def recv(self, length):
            if not self.data:
                stop.set()
                raise socket.timeout()
            return super().recv(length)

    protocol = ScrcpyProtocol(Idle(header()), stop)
    protocol.read_header()
    with pytest.raises(StreamCancelled):
        protocol.read_packet()


def test_idle_timeouts_do_not_disconnect_static_screen():
    class IdleThenData(Fragments):
        def __init__(self, data):
            super().__init__(data)
            self.timeouts = 3

        def recv(self, length):
            if self.timeouts:
                self.timeouts -= 1
                raise socket.timeout()
            return super().recv(length)

    protocol = ScrcpyProtocol(IdleThenData(header() + struct.pack(">QI", 9, 1) + b"a"), threading.Event())
    assert protocol.read_header().codec == "h264"
    assert protocol.read_packet().data == b"a"


def test_partial_packet_times_out(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.streaming.protocol.time.monotonic", lambda: clock[0])

    class Partial(Fragments):
        def recv(self, length):
            if self.data:
                return super().recv(length)
            clock[0] += 0.6
            raise socket.timeout()

    protocol = ScrcpyProtocol(Partial(header() + b"\0"), threading.Event(), read_timeout=1)
    protocol.read_header()
    with pytest.raises(ProtocolError, match="Timed out"):
        protocol.read_packet()


def test_startup_timeouts_are_bounded(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.streaming.protocol.time.monotonic", lambda: clock[0])

    class NeverReady:
        def recv(self, length):
            clock[0] += 0.6
            raise socket.timeout()

    with pytest.raises(ProtocolError, match="Timed out"):
        ScrcpyProtocol(NeverReady(), threading.Event(), read_timeout=1).read_header()


@pytest.mark.parametrize("config_packets", [0, 1, 3])
def test_first_media_deadline_survives_config_only_packets(monkeypatch, config_packets):
    clock = [0.0]
    monkeypatch.setattr("app.streaming.protocol.time.monotonic", lambda: clock[0])

    class IdleAfterData(Fragments):
        def recv(self, length):
            if self.data:
                return super().recv(length)
            clock[0] += 0.6
            raise socket.timeout()

    wire = header() + (struct.pack(">QI", PACKET_FLAG_CONFIG, 3) + b"sps") * config_packets
    protocol = ScrcpyProtocol(IdleAfterData(wire), threading.Event(), read_timeout=1)
    protocol.read_header()
    for _ in range(config_packets):
        clock[0] += 0.1
        assert protocol.read_packet().is_config
    with pytest.raises(ProtocolError, match="Timed out"):
        protocol.read_packet()
    assert clock[0] < 2


def test_established_static_stream_can_idle_beyond_startup_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.streaming.protocol.time.monotonic", lambda: clock[0])

    class StaticThenChanged(Fragments):
        idle = 3
        def recv(self, length):
            if not self.data and self.idle:
                self.idle -= 1
                clock[0] += 100
                raise socket.timeout()
            if not self.data:
                self.data = struct.pack(">QI", 2, 1) + b"b"
            return super().recv(length)

    protocol = ScrcpyProtocol(StaticThenChanged(header() + struct.pack(">QI", 1, 1) + b"a"), threading.Event(), read_timeout=1)
    protocol.read_header()
    assert protocol.read_packet().data == b"a"
    assert protocol.read_packet().data == b"b"
    assert clock[0] == 300


def test_session_may_bound_first_decoded_frame_even_after_media(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.streaming.protocol.time.monotonic", lambda: clock[0])

    class IdleAfterMedia(Fragments):
        def recv(self, length):
            if self.data:
                return super().recv(length)
            clock[0] += 0.6
            raise socket.timeout()

    protocol = ScrcpyProtocol(IdleAfterMedia(header() + struct.pack(">QI", 1, 1) + b"a"), threading.Event(), read_timeout=1)
    protocol.read_header()
    assert protocol.read_packet(allow_idle=False).data == b"a"
    with pytest.raises(ProtocolError, match="Timed out"):
        protocol.read_packet(allow_idle=False)


def test_connection_error_respects_cancellation():
    stop = threading.Event()

    class Broken:
        def recv(self, length):
            raise ConnectionResetError("reset")

    protocol = ScrcpyProtocol(Broken(), stop)
    with pytest.raises(StreamClosed, match="reset"):
        protocol.read_header()
    stop.set()
    with pytest.raises(StreamCancelled):
        protocol.read_header()


@pytest.mark.parametrize("options", [
    {"read_timeout": 0}, {"read_timeout": float("nan")}, {"read_timeout": True},
    {"max_packet_bytes": 0}, {"max_packet_bytes": True}, {"max_packet_bytes": MAX_PACKET_BYTES + 1},
    {"expect_dummy": 1},
])
def test_invalid_reader_options(options):
    with pytest.raises(ValueError):
        reader(header(), **options)
