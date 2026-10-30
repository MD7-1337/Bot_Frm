"""Bounded, serial-specific ADB operations without a host shell.

All device operations require a verified connection serial. ADB's global
``devices`` and ``version`` operations are the only calls without ``-s``.
This adapter does not claim that USB permission or authorization is available.
"""

from __future__ import annotations

import math
import re
import struct
import subprocess
import threading
import time
from dataclasses import dataclass


class AdbError(RuntimeError):
    """ADB could not be found, timed out, or returned an unsuccessful result."""


class AdbTimeout(AdbError):
    """The configured ADB operation deadline expired."""


class AdbCaptureError(AdbError):
    """The device did not return a supported screenshot image."""


class AdbUnsupportedOperation(AdbError):
    """The requested command cannot be represented by this ADB backend."""


class DeviceUnavailable(AdbError):
    """The selected device is disconnected, offline, or unauthorized."""

    state = "disconnected"


class DeviceUnauthorized(DeviceUnavailable):
    state = "unauthorized"


class DeviceOffline(DeviceUnavailable):
    state = "offline"


class DevicePermissionDenied(DeviceUnavailable):
    state = "no permissions"


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    state: str
    model: str | None = None
    generation: int = 0

    @property
    def available(self) -> bool:
        return self.state == "device"


@dataclass(frozen=True)
class ScreenInfo:
    """Current screenshot dimensions and observed display rotation in degrees.

    Dimensions are taken from the unscaled device PNG, not ``wm size`` (which
    can report a natural/override size with a different current orientation).
    Rotation is None if this Android build does not expose a recognized value.
    """

    width: int
    height: int
    orientation: int | None = None


def png_dimensions(image: bytes) -> tuple[int, int]:
    if (len(image) < 33 or image[:8] != b"\x89PNG\r\n\x1a\n"
            or image[8:12] != b"\x00\x00\x00\r" or image[12:16] != b"IHDR"):
        raise AdbCaptureError("Device screencap returned an invalid PNG image header.")
    width, height = struct.unpack(">II", image[16:24])
    if not (0 < width <= 16_384 and 0 < height <= 16_384 and width * height <= 100_000_000):
        raise AdbCaptureError("Device screenshot dimensions are unsupported.")
    return width, height


def parse_orientation(output: str) -> int | None:
    """Parse observed Android display rotation, never infer it from aspect ratio."""
    # SurfaceOrientation is exposed by older dumpsys input versions. Newer
    # versions may report a default display viewport orientation or ROTATION_N.
    patterns = (
        r"\bSurfaceOrientation:\s*([0-3])\b",
        r"\bmCurrentRotation\s*=\s*ROTATION_(0|90|180|270)\b",
        r"\b(?:displayId|displayId=)\s*=?\s*0\b[^\r\n]*?\borientation[=:]\s*([0-3])\b",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, output)
        if match:
            value = int(match.group(1))
            return value if index == 1 else value * 90
    return None


def validate_serial(serial: str) -> str:
    if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9_\[\]][A-Za-z0-9_.:\[\]-]{0,255}", serial):
        raise ValueError("Select a valid ADB serial from device discovery.")
    return serial


def _coordinate(value: int) -> str:
    if type(value) is not int or not 0 <= value <= 100_000:
        raise ValueError("Coordinates must be integers between 0 and 100000.")
    return str(value)


def validate_package(package: str) -> str:
    """Validate an Android application ID before any remote-shell operation."""
    if (not isinstance(package, str) or len(package) > 255
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", package) is None):
        raise ValueError("Use an Android application ID such as com.example.app.")
    return package


def encode_input_text(text: str) -> str:
    """Represent a conservative ASCII subset for Android's input text command.

    adb shell joins command arguments through Android's shell. A host argv list
    alone does not protect that second shell, so metacharacters, percent escapes,
    quotes, control characters and Unicode are explicitly unsupported here.
    Spaces use Android input's documented %s representation.
    """
    if not isinstance(text, str):
        raise ValueError("Text must be a string.")
    if len(text) > 4096:
        raise ValueError("Text must not exceed 4096 characters.")
    if re.fullmatch(r"[A-Za-z0-9 ,.@_:/+\-]*", text) is None:
        raise AdbUnsupportedOperation(
            "ADB text input supports ASCII letters, digits, spaces and ,.@_:/+- only; "
            "Unicode, percent sequences and shell metacharacters require another input method.")
    return text.replace(" ", "%s")


def _android_error(output: str) -> bool:
    """Recognize explicit shell-command failures even on Android exit status 0.

    Android builds differ in whether shell entry points propagate failures as
    process exit codes. Do not treat a printed Java exception as acceptance of
    an input or application-control operation.
    """
    return re.search(r"\bError:|\b(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_]*Exception\b",
                     output, re.IGNORECASE) is not None


def _check_android_output(output: bytes, operation: str) -> None:
    decoded = output.decode("utf-8", errors="replace")
    if _android_error(decoded):
        raise AdbError(f"Android {operation} failed: {decoded.strip()[:1000]}")


class AdbClient:
    def __init__(self, executable: str = "adb", timeout: float = 10) -> None:
        if not isinstance(executable, str) or not executable or "\x00" in executable:
            raise ValueError("ADB executable must be a nonempty path.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError("ADB timeout must be greater than 0 and at most 300 seconds.")
        self.executable = executable
        self.timeout = timeout
        self._locks: dict[str, threading.RLock] = {}
        self._lock = threading.Lock()

    def _run(self, arguments: list[str]) -> bytes:
        try:
            result = subprocess.run(
                [self.executable, *arguments],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
                shell=False,
            )
        except FileNotFoundError as error:
            raise AdbError("ADB not found. Configure the Android platform-tools adb executable.") from error
        except subprocess.TimeoutExpired as error:
            raise AdbTimeout(f"ADB operation timed out after {self.timeout:g} seconds.") from error
        except OSError as error:
            raise AdbError(f"Could not launch ADB: {error}") from error
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:2000]
        if result.returncode or _android_error(detail):
            lowered = detail.lower()
            if "unauthorized" in lowered or "authorizing" in lowered:
                raise DeviceUnauthorized(detail)
            if "offline" in lowered:
                raise DeviceOffline(detail)
            if "no permissions" in lowered or "insufficient permissions" in lowered:
                raise DevicePermissionDenied(detail)
            if ("no devices" in lowered or lowered in ("error: closed", "closed")
                    or ("device" in lowered and any(word in lowered for word in ("not found", "disconnected", "closed")))):
                raise DeviceUnavailable(detail or "Selected device is unavailable.")
            raise AdbError(f"ADB exited with status {result.returncode}: {detail}")
        return result.stdout

    def _device(self, serial: str, *arguments: str) -> bytes:
        serial = validate_serial(serial)
        with self._device_lock(serial):
            return self._run(["-s", serial, *arguments])

    def _device_lock(self, serial: str) -> threading.RLock:
        with self._lock:
            return self._locks.setdefault(serial, threading.RLock())

    def version(self) -> str:
        return self._run(["version"]).decode("utf-8", errors="replace").strip()

    def devices(self) -> list[DeviceInfo]:
        result: list[DeviceInfo] = []
        output = self._run(["devices", "-l"]).decode("utf-8", errors="replace")
        lines = output.splitlines()
        header = next((index for index, line in enumerate(lines) if line.strip() == "List of devices attached"), None)
        if header is None:
            raise AdbError("ADB discovery returned no device-list header; connection state is unknown.")
        seen: set[str] = set()
        for line in lines[header + 1:]:
            parts = line.strip().split()
            if len(parts) < 2 or parts[0] in ("List", "adb:") or parts[0].startswith("*"):
                continue
            # The long listing may contain product/device/transport_id fields.
            try:
                validate_serial(parts[0])
            except ValueError:
                continue
            if parts[0] in seen:
                raise AdbError("ADB discovery reported duplicate serials; refusing an ambiguous device list.")
            seen.add(parts[0])
            model = next((part[6:] for part in parts[2:] if part.startswith("model:")), None)
            states = {"device", "offline", "unauthorized", "recovery", "rescue", "sideload", "bootloader", "host", "authorizing", "connecting"}
            state = "no permissions" if parts[1] == "no" else parts[1] if parts[1] in states else "unknown"
            result.append(DeviceInfo(parts[0], state, model))
        return result

    def screenshot(self, serial: str) -> bytes:
        image = self._device(serial, "exec-out", "screencap", "-p")
        png_dimensions(image)
        return image

    def state(self, serial: str) -> str:
        """Return a specific observed state; transport/protocol errors still raise."""
        try:
            output = self._device(serial, "get-state").decode("utf-8", errors="replace").strip()
        except DeviceUnavailable as error:
            return error.state
        return output if output in {"device", "offline", "unauthorized", "recovery", "rescue", "sideload", "bootloader", "authorizing", "connecting"} else "unknown"

    def resolution(self, serial: str) -> tuple[int, int]:
        """Current full screenshot width and height in Android pixel coordinates."""
        return png_dimensions(self.screenshot(serial))

    def orientation(self, serial: str) -> int | None:
        """Observed default-display rotation; unavailable metadata returns None."""
        try:
            output = self._device(serial, "shell", "dumpsys", "input")
        except DeviceUnavailable:
            raise
        except AdbError:
            return None
        return parse_orientation(output.decode("utf-8", errors="replace"))

    def screen_info(self, serial: str) -> ScreenInfo:
        width, height = self.resolution(serial)
        return ScreenInfo(width, height, self.orientation(serial))

    def tap(self, serial: str, x: int, y: int) -> None:
        output = self._device(serial, "shell", "input", "tap", _coordinate(x), _coordinate(y))
        _check_android_output(output, "tap")

    def double_tap(self, serial: str, x: int, y: int, interval: float = 0.12) -> None:
        """Two serialized taps with a bounded inter-tap delay in seconds.

        Invoke off the GUI thread. Android/app recognition of a double tap is
        app-dependent; these are two actual input commands, never a fake result.
        """
        validate_serial(serial)
        _coordinate(x)
        _coordinate(y)
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or not 0 <= interval <= 1:
            raise ValueError("Double-tap interval must be finite seconds between 0 and 1.")
        with self._device_lock(serial):
            self.tap(serial, x, y)
            time.sleep(interval)
            self.tap(serial, x, y)

    def long_press(self, serial: str, x: int, y: int, duration_ms: int = 800) -> None:
        """Use Android input's supported stationary swipe to hold then release."""
        self.swipe(serial, x, y, x, y, duration_ms)

    def drag(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None:
        """Press/move/release via Android input swipe, not a raw touch event path."""
        self.swipe(serial, x1, y1, x2, y2, duration_ms)

    def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None:
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60_000:
            raise ValueError("Swipe duration must be an integer between 1 and 60000 milliseconds.")
        output = self._device(serial, "shell", "input", "swipe", *map(_coordinate, (x1, y1, x2, y2)), str(duration_ms))
        _check_android_output(output, "swipe")

    def key(self, serial: str, key: str) -> None:
        # Never forward arbitrary remote-shell text; Android input accepts these
        # symbolic key names and numeric keycodes without quoting surprises.
        if not isinstance(key, str) or not re.fullmatch(r"(?:KEYCODE_)?[A-Z][A-Z0-9_]{0,63}|[0-9]{1,3}", key):
            raise ValueError("Use an Android key name such as HOME, BACK, ENTER or KEYCODE_BACK.")
        output = self._device(serial, "shell", "input", "keyevent", key)
        _check_android_output(output, "key input")

    def launch_app(self, serial: str, package: str) -> None:
        """Resolve and launch the actual MAIN/LAUNCHER activity with a deadline.

        Requires Android's package-manager resolve-activity command. A valid
        package with no exported launcher produces an error rather than success.
        am start -W must report Status: ok; that means Android accepted startup,
        not that an application-specific loading screen finished.
        """
        package = validate_package(package)
        with self._device_lock(validate_serial(serial)):
            resolved = self._device(serial, "shell", "cmd", "package", "resolve-activity", "--brief",
                                    "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                                    package).decode("utf-8", errors="replace")
            if _android_error(resolved):
                raise AdbError(f"Android could not resolve {package}: {resolved.strip()[:1000]}")
            # Component names are generated by Android but still cross the
            # shell boundary. Do not forward arbitrary output or Java $ names.
            pattern = re.compile(re.escape(package) + r"/\.?[A-Za-z_][A-Za-z0-9_.]*")
            components = [line.strip() for line in resolved.splitlines() if pattern.fullmatch(line.strip())]
            if len(components) != 1:
                raise AdbError(f"Could not resolve one supported launcher activity for {package}.")
            output = self._device(serial, "shell", "am", "start", "-W", "-n", components[0]).decode("utf-8", errors="replace")
            if (re.search(r"^\s*Status:\s*ok\s*$", output, re.MULTILINE | re.IGNORECASE) is None
                    or _android_error(output)):
                raise AdbError(f"Android did not confirm launch of {package}: {output.strip()[:1000]}")

    def stop_app(self, serial: str, package: str) -> None:
        """Force-stop a known installed package; never infer installation."""
        package = validate_package(package)
        with self._device_lock(validate_serial(serial)):
            locations = self._device(serial, "shell", "pm", "path", package).decode("utf-8", errors="replace")
            if _android_error(locations):
                raise AdbError(f"Android could not inspect {package}: {locations.strip()[:1000]}")
            if not any(line.strip().startswith("package:") for line in locations.splitlines()):
                raise AdbError(f"Android package {package} is not installed or its package path is unavailable.")
            output = self._device(serial, "shell", "am", "force-stop", package).decode("utf-8", errors="replace")
            if _android_error(output):
                raise AdbError(f"Android could not stop {package}: {output.strip()[:1000]}")

    def type_text(self, serial: str, text: str) -> None:
        """Type the supported ASCII subset; reject unsupported text before I/O."""
        encoded = encode_input_text(text)
        validate_serial(serial)
        if not encoded:
            return
        output = self._device(serial, "shell", "input", "text", encoded).decode("utf-8", errors="replace")
        if _android_error(output):
            raise AdbError(f"Android text input failed: {output.strip()[:1000]}")
