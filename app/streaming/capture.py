"""One-shot screenshot fallback; call capture from a background worker.

This provides real ADB PNG frames, not a scrcpy video stream. Consumers may
share the most recent immutable frame. The UI must not call ADB synchronously.
"""

from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass

from app.devices.adb import AdbClient, AdbError


@dataclass(frozen=True)
class ScreenFrame:
    serial: str
    png: bytes
    width: int
    height: int
    captured_at: float


class CaptureService:
    def __init__(self, client: AdbClient) -> None:
        self.client = client
        self._latest: dict[str, ScreenFrame] = {}
        self._lock = threading.Lock()

    def capture(self, serial: str) -> ScreenFrame:
        png = self.client.screenshot(serial)
        if len(png) < 33 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
            raise AdbError("Screenshot is missing its PNG image header.")
        width, height = struct.unpack(">II", png[16:24])
        if not (0 < width <= 16_384 and 0 < height <= 16_384 and width * height <= 100_000_000):
            raise AdbError("Screenshot dimensions are unsupported.")
        frame = ScreenFrame(serial, png, width, height, time.monotonic())
        with self._lock:
            self._latest[serial] = frame
        return frame

    def latest(self, serial: str) -> ScreenFrame | None:
        with self._lock:
            return self._latest.get(serial)

    def forget(self, serial: str) -> None:
        with self._lock:
            self._latest.pop(serial, None)
