"""H.264 decoding for the pinned scrcpy video packet stream.

The Android server emits codec-config packets separately. As upstream's v3.1
demuxer does, append pending config bytes to the next media packet before
passing it to FFmpeg. No Qt objects or UI work occur here.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import av


class DecodeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    rgb: bytes
    width: int
    height: int


class H264Decoder:
    def __init__(self, *, max_pixels: int = 16_777_216, max_config_bytes: int = 1_048_576):
        if type(max_pixels) is not int or max_pixels < 1 or type(max_config_bytes) is not int or max_config_bytes < 1:
            raise ValueError("Decoder size limits must be positive integers")
        self.max_pixels = max_pixels
        self.max_config_bytes = max_config_bytes
        self._codec = av.CodecContext.create("h264", "r")
        self._codec.thread_count = 1
        self._config = b""

    def decode(self, packet) -> list[DecodedFrame]:
        if self._codec is None:
            raise DecodeError("Decoder has been closed")
        if packet.is_config:
            if len(self._config) + len(packet.data) > self.max_config_bytes:
                raise DecodeError("H.264 configuration exceeds size limit")
            self._config += packet.data
            return []
        data = self._config + packet.data
        self._config = b""
        media = av.Packet(data)
        media.pts = packet.pts_us
        media.dts = packet.pts_us
        media.time_base = Fraction(1, 1_000_000)
        try:
            decoded = self._codec.decode(media)
            output = []
            for frame in decoded:
                if frame.width <= 0 or frame.height <= 0 or frame.width * frame.height > self.max_pixels:
                    raise DecodeError("Decoded video frame dimensions exceed the configured limit")
                rgb = frame.to_ndarray(format="rgb24")
                output.append(DecodedFrame(rgb.tobytes(), frame.width, frame.height))
            return output
        except av.FFmpegError as error:
            raise DecodeError(f"H.264 decoder rejected the stream: {error}") from error

    def close(self):
        self._config = b""
        self._codec = None
