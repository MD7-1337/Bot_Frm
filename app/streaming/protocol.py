"""Bounded reader for the pinned scrcpy 3.1 video-only forward tunnel.

Wire contract verified against the upstream v3.1 implementation:
https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/device/DesktopConnection.java
https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/device/Streamer.java
https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/video/VideoCodec.java
https://github.com/Genymobile/scrcpy/blob/v3.1/app/src/demuxer.c

Assumptions: one video socket, tunnel_forward=true, audio=false, control=false,
send_dummy_byte=true, send_device_meta=true, send_codec_meta=true,
send_frame_meta=true, video_codec=h264. No audio/control framing is accepted.
After initial media arrives an unchanged Android screen may legitimately send
no new packets. First media, startup metadata and partially received records
have deadlines; codec-configuration packets never extend the startup deadline.
The owning session must set a short socket recv timeout to make cancellation
responsive and close the socket during teardown.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import socket
import struct
import threading
import time
from typing import Protocol

H264_CODEC_ID = 0x68323634
PACKET_FLAG_CONFIG = 1 << 63
PACKET_FLAG_KEY_FRAME = 1 << 62
PACKET_PTS_MASK = PACKET_FLAG_KEY_FRAME - 1
MAX_PACKET_BYTES = 16 * 1024 * 1024
MAX_DIMENSION = 16_384
MAX_PIXELS = 32_000_000


class ProtocolError(RuntimeError):
    """The stream violates the supported scrcpy version/codec/size contract."""


class StreamClosed(ConnectionError):
    """The owned video connection ended or failed before a complete record."""


class StreamCancelled(Exception):
    """The owning session requested cancellation."""


class _ReadableSocket(Protocol):
    def recv(self, length: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class VideoHeader:
    device_name: str
    codec: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class VideoPacket:
    data: bytes
    pts_us: int | None
    is_config: bool = False
    is_keyframe: bool = False


def validate_dimensions(width: int, height: int) -> None:
    """Validate metadata before a decoder or renderer allocates frame buffers."""
    if (type(width) is not int or type(height) is not int
            or not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION
            or width * height > MAX_PIXELS):
        raise ProtocolError("Video dimensions exceed the supported frame limits")


class ScrcpyProtocol:
    """Read exact binary records, tolerating arbitrary TCP fragmentation.

    ``read_timeout`` is the deadline in seconds to complete startup records or
    a partially received frame record. After media arrives, the next packet may
    remain wholly idle until cancellation; an Android static screen is not a
    fault. A session may explicitly keep startup bounded until decoding succeeds.
    Only the session reader thread should invoke these methods.

    Set ``expect_dummy=False`` only when the owning transport has already read
    and verified the forward-tunnel dummy byte while checking server readiness.
    """

    def __init__(
        self, sock: _ReadableSocket, stop_event: threading.Event, *,
        max_packet_bytes: int = MAX_PACKET_BYTES, read_timeout: float = 10.0,
        expect_dummy: bool = True,
    ) -> None:
        if type(max_packet_bytes) is not int or not 1 <= max_packet_bytes <= MAX_PACKET_BYTES:
            raise ValueError(f"max_packet_bytes must be an integer in [1, {MAX_PACKET_BYTES}]")
        if (isinstance(read_timeout, bool) or not isinstance(read_timeout, (int, float))
                or not math.isfinite(read_timeout) or not 0 < read_timeout <= 300):
            raise ValueError("read_timeout must be finite seconds in (0, 300]")
        if type(expect_dummy) is not bool:
            raise ValueError("expect_dummy must be a boolean")
        self.sock = sock
        self.stop_event = stop_event
        self.max_packet_bytes = max_packet_bytes
        self.read_timeout = float(read_timeout)
        self.expect_dummy = expect_dummy
        self._header_read = False
        self._media_seen = False
        self._startup_deadline = None

    def _exact(self, length: int, *, allow_idle: bool = False, absolute_deadline: float | None = None) -> bytes:
        result = bytearray()
        deadline = (absolute_deadline if absolute_deadline is not None else
                    None if allow_idle else time.monotonic() + self.read_timeout)
        while len(result) < length:
            if self.stop_event.is_set():
                raise StreamCancelled("Video session was cancelled")
            if deadline is not None and time.monotonic() >= deadline:
                raise ProtocolError("Timed out receiving a complete scrcpy record")
            try:
                chunk = self.sock.recv(length - len(result))
            except socket.timeout:
                continue
            except OSError as error:
                if self.stop_event.is_set():
                    raise StreamCancelled("Video session was cancelled") from error
                raise StreamClosed(f"Video connection failed: {error}") from error
            if not chunk:
                if self.stop_event.is_set():
                    raise StreamCancelled("Video session was cancelled")
                raise StreamClosed(f"Video connection closed after {len(result)} of {length} bytes")
            if not isinstance(chunk, bytes) or len(chunk) > length - len(result):
                raise ProtocolError("Socket returned an invalid record fragment")
            result.extend(chunk)
            if deadline is None:
                deadline = time.monotonic() + self.read_timeout
        return bytes(result)

    def read_header(self) -> VideoHeader:
        """Consume optional dummy byte, device name and H.264 metadata once."""
        if self._header_read:
            raise ProtocolError("Video metadata has already been read")
        if self.expect_dummy and self._exact(1) != b"\x00":
            raise ProtocolError("Unexpected forward-tunnel connection byte")
        name_field = self._exact(64)
        if b"\x00" not in name_field:
            raise ProtocolError("Device name lacks its expected terminator")
        try:
            name = name_field.split(b"\x00", 1)[0].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ProtocolError("Device name is not valid UTF-8") from error
        # Read codec before dimensions: disabled/configuration-error streams
        # send only their 4-byte code, not the full video metadata record.
        codec_id, = struct.unpack(">I", self._exact(4))
        if codec_id != H264_CODEC_ID:
            if codec_id in (0, 1):
                raise ProtocolError("Device disabled video or reported a stream configuration error")
            raise ProtocolError(f"Unsupported video codec ID 0x{codec_id:08x}; expected H.264")
        width, height = struct.unpack(">II", self._exact(8))
        validate_dimensions(width, height)
        self._header_read = True
        self._startup_deadline = time.monotonic() + self.read_timeout
        return VideoHeader(name, "h264", width, height)

    def read_packet(self, *, allow_idle: bool | None = None) -> VideoPacket:
        """Read a packet; bound startup until media (or explicit session ready).

        ``allow_idle=False`` retains the original first-media deadline even if
        a prior media packet arrived but has not yielded a decoded frame yet.
        This lets the session bound its first displayed frame as well.
        """
        if not self._header_read:
            raise ProtocolError("Read video metadata before reading packets")
        if allow_idle is None:
            allow_idle = self._media_seen
        elif type(allow_idle) is not bool:
            raise ValueError("allow_idle must be a boolean or None")
        deadline = None if allow_idle else self._startup_deadline
        pts_flags, length = struct.unpack(">QI", self._exact(12, allow_idle=allow_idle, absolute_deadline=deadline))
        if not 0 < length <= self.max_packet_bytes:
            raise ProtocolError(f"Encoded packet size {length} exceeds supported limits")
        payload = self._exact(length, absolute_deadline=deadline)
        config = bool(pts_flags & PACKET_FLAG_CONFIG)
        if not config:
            self._media_seen = True
        pts = None if config else pts_flags & PACKET_PTS_MASK
        return VideoPacket(payload, pts, config, bool(pts_flags & PACKET_FLAG_KEY_FRAME))
