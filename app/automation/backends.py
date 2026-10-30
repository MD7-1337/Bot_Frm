"""Serial-bound adapters used by the scripting API, with explicit test fixtures.

Backends perform operations and return actual pixels. The Device API owns action
events, cancellation checkpoints and screen-bound coordinate validation. A mock
backend is never selected by the production GUI and emits no fake device state.
"""
from __future__ import annotations

from collections.abc import Callable
import re
from pathlib import Path
from typing import Any, TypeVar

import cv2
import numpy as np

from app.devices.adb import (
    AdbCaptureError, AdbClient, AdbError, AdbTimeout, AdbUnsupportedOperation,
    DeviceOffline as AdbDeviceOffline, DevicePermissionDenied,
    DeviceUnauthorized as AdbDeviceUnauthorized, DeviceUnavailable,
    encode_input_text, png_dimensions, validate_package, validate_serial,
)

T = TypeVar("T")


def _errors():
    # Keep the device transport free from an import cycle through api.Device.
    from app.automation.api import errors
    return errors


def _decode_png(payload: bytes) -> np.ndarray:
    errors = _errors()
    if not isinstance(payload, bytes) or len(payload) > 100_000_000:
        raise errors.FrameUnavailable("Screenshot data is invalid or exceeds the supported limit")
    # Validate the advertised PNG dimensions before invoking a native decoder.
    # The live ADB adapter already does this, but explicit fixture files use the
    # same boundary and must not silently accept JPEGs or oversized PNG headers.
    try:
        png_dimensions(payload)
    except AdbCaptureError as error:
        raise errors.FrameUnavailable(str(error)) from error
    try:
        image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as error:
        raise errors.FrameUnavailable("Screenshot PNG could not be decoded") from error
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise errors.FrameUnavailable("Screenshot PNG could not be decoded")
    if image.shape[0] > 16_384 or image.shape[1] > 16_384 or image.shape[0] * image.shape[1] > 100_000_000:
        raise errors.FrameUnavailable("Screenshot dimensions exceed the supported limit")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


class AdbBackend:
    """One immutable serial assignment using the existing validated ADB client."""

    def __init__(self, serial: str, adb_executable: str = "adb"):
        self._serial = validate_serial(serial)
        self._adb = AdbClient(adb_executable)

    @property
    def serial(self) -> str:
        return self._serial

    def _invoke(self, operation: Callable[[], T]) -> T:
        errors = _errors()
        try:
            return operation()
        except AdbDeviceUnauthorized as error:
            raise errors.DeviceUnauthorized(str(error)) from error
        except AdbDeviceOffline as error:
            raise errors.DeviceOffline(str(error)) from error
        except DevicePermissionDenied as error:
            raise errors.CommandFailed(str(error)) from error
        except DeviceUnavailable as error:
            raise errors.DeviceDisconnected(str(error)) from error
        except AdbTimeout as error:
            raise errors.CommandTimeout(str(error)) from error
        except AdbCaptureError as error:
            raise errors.FrameUnavailable(str(error)) from error
        except AdbUnsupportedOperation as error:
            raise errors.UnsupportedCapability(str(error)) from error
        except AdbError as error:
            raise errors.CommandFailed(str(error)) from error

    def capture(self) -> np.ndarray:
        return _decode_png(self._invoke(lambda: self._adb.screenshot(self.serial)))

    def tap(self, x: int, y: int) -> None:
        self._invoke(lambda: self._adb.tap(self.serial, x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None:
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60_000:
            raise ValueError("Swipe duration must be integer milliseconds in [1, 60000]")
        if any(type(value) is not int or not 0 <= value <= 100_000 for value in (x1, y1, x2, y2)):
            raise ValueError("Swipe coordinates must be integer device pixels between 0 and 100000")
        # This adapter owns a client for one immutable serial. Keep the existing
        # serial RLock through the temporary deadline change so another action
        # on this backend cannot inherit the longer gesture timeout. Do not
        # change shared multi-device GUI clients or create a second ADB client.
        def operation():
            with self._adb._device_lock(self.serial):
                original_timeout = self._adb.timeout
                self._adb.timeout = max(10, original_timeout, duration_ms / 1000 + 2)
                try:
                    self._adb.swipe(self.serial, x1, y1, x2, y2, duration_ms)
                finally:
                    self._adb.timeout = original_timeout
        self._invoke(operation)

    def key(self, key: str) -> None:
        self._invoke(lambda: self._adb.key(self.serial, key))

    def launch_app(self, package: str) -> None:
        self._invoke(lambda: self._adb.launch_app(self.serial, package))

    def stop_app(self, package: str) -> None:
        self._invoke(lambda: self._adb.stop_app(self.serial, package))

    def type_text(self, text: str) -> None:
        self._invoke(lambda: self._adb.type_text(self.serial, text))


class MockBackend:
    """Explicit deterministic fixture adapter, not a simulated production phone.

    Config contains JSON primitives only:
    - resolution: [width, height], default [1080, 1920] for a zero RGB frame;
    - frame_paths: PNG paths consumed per capture, repeating the final frame;
    - disconnect_after: number of successful captures before later operations
      raise DeviceDisconnected, or None to stay connected.

    Files are decoded lazily. Every returned ndarray is owned by the caller.
    No backend emits action events; the same Device API does that for both
    adapters after the operation succeeds.
    """

    def __init__(self, serial: str, config: dict[str, Any] | None = None):
        self._serial = validate_serial(serial)
        if config is None:
            config = {}
        if not isinstance(config, dict) or set(config) - {"resolution", "frame_paths", "disconnect_after"}:
            raise ValueError("Unsupported mock backend configuration")
        resolution = config.get("resolution", [1080, 1920])
        if (not isinstance(resolution, list) or len(resolution) != 2
                or any(type(value) is not int or not 0 < value <= 16_384 for value in resolution)
                or resolution[0] * resolution[1] > 100_000_000):
            raise ValueError("Mock resolution must be [width, height] within supported dimensions")
        paths = config.get("frame_paths", [])
        if (not isinstance(paths, list) or len(paths) > 256
                or any(not isinstance(path, str) or not path or "\x00" in path or len(path) > 4096 for path in paths)):
            raise ValueError("Mock frame_paths must contain at most 256 PNG path strings")
        disconnect = config.get("disconnect_after")
        if disconnect is not None and (type(disconnect) is not int or disconnect < 0):
            raise ValueError("Mock disconnect_after must be a nonnegative integer or None")
        self._resolution = tuple(resolution)
        self._paths = tuple(Path(path) for path in paths)
        self._disconnect_after = disconnect
        self._captures = 0

    @property
    def serial(self) -> str:
        return self._serial

    def _check_connected(self) -> None:
        if self._disconnect_after is not None and self._captures >= self._disconnect_after:
            raise _errors().DeviceDisconnected(f"Explicit mock fixture {self.serial} disconnected")

    def capture(self) -> np.ndarray:
        self._check_connected()
        if self._paths:
            path = self._paths[min(self._captures, len(self._paths) - 1)]
            try:
                if path.stat().st_size > 100_000_000:
                    raise _errors().FrameUnavailable("Mock PNG fixture exceeds the supported limit")
                frame = _decode_png(path.read_bytes())
            except OSError as error:
                raise _errors().FrameUnavailable(f"Could not read explicit mock PNG fixture: {path}") from error
        else:
            width, height = self._resolution
            frame = np.zeros((height, width, 3), dtype=np.uint8)
        self._captures += 1
        return frame

    def tap(self, x: int, y: int) -> None:
        self._check_connected()
        self._coordinate(x)
        self._coordinate(y)

    @staticmethod
    def _coordinate(value: int) -> None:
        if type(value) is not int or not 0 <= value <= 100_000:
            raise _errors().InvalidCoordinates("Coordinates must be integer device pixels between 0 and 100000")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None:
        self._check_connected()
        for coordinate in (x1, y1, x2, y2):
            self._coordinate(coordinate)
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60_000:
            raise ValueError("Swipe duration must be integer milliseconds in [1, 60000]")

    def key(self, key: str) -> None:
        self._check_connected()
        if not isinstance(key, str) or not re.fullmatch(r"(?:KEYCODE_)?[A-Z][A-Z0-9_]{0,63}|[0-9]{1,3}", key):
            raise ValueError("Use an Android key name such as KEYCODE_HOME")

    def launch_app(self, package: str) -> None:
        self._check_connected()
        validate_package(package)

    def stop_app(self, package: str) -> None:
        self._check_connected()
        validate_package(package)

    def type_text(self, text: str) -> None:
        self._check_connected()
        try:
            encode_input_text(text)
        except AdbUnsupportedOperation as error:
            raise _errors().UnsupportedCapability(str(error)) from error
