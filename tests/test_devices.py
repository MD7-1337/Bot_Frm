from __future__ import annotations

import struct
import subprocess
import zlib
from unittest.mock import Mock

import pytest

from app.devices.adb import AdbClient, AdbError, DeviceUnavailable
from app.streaming.capture import CaptureService
from app.streaming.scrcpy import ExternalScrcpy, ScrcpyError


def png_image(width: int = 2, height: int = 3) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\x00\x00" * width) * height)) + chunk(b"IEND", b"")


def patch_run(monkeypatch, stdout=b"", stderr=b"", returncode=0):
    run = Mock(return_value=subprocess.CompletedProcess([], returncode, stdout, stderr))
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    return run


def test_devices_include_unavailable_states_without_invented_metadata(monkeypatch):
    run = patch_run(monkeypatch, b"List of devices attached\nUSB1 device product:test model:Pixel_8 device:test transport_id:1\n192.168.1.10:5555 offline\nUSB2 unauthorized\nUSB3 no permissions (user lacks permission)\n")
    devices = AdbClient().devices()
    assert [(d.serial, d.state, d.model) for d in devices] == [
        ("USB1", "device", "Pixel_8"), ("192.168.1.10:5555", "offline", None),
        ("USB2", "unauthorized", None), ("USB3", "no permissions", None),
    ]
    assert devices[0].available and not devices[1].available
    assert run.call_args.args[0] == ["adb", "devices", "-l"]


@pytest.mark.parametrize("method,arguments,tail", [
    ("tap", (10, 20), ["shell", "input", "tap", "10", "20"]),
    ("swipe", (1, 2, 3, 4, 700), ["shell", "input", "swipe", "1", "2", "3", "4", "700"]),
    ("key", ("HOME",), ["shell", "input", "keyevent", "HOME"]),
    ("screenshot", (), ["exec-out", "screencap", "-p"]),
])
def test_commands_always_select_serial(monkeypatch, method, arguments, tail):
    run = patch_run(monkeypatch, png_image())
    getattr(AdbClient("/opt/platform-tools/adb", timeout=4), method)("PHONE2", *arguments)
    assert run.call_args.args[0] == ["/opt/platform-tools/adb", "-s", "PHONE2", *tail]
    assert run.call_args.kwargs["timeout"] == 4
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize("serial", ["", "-d", "phone;rm", "phone\nother", "x y", "$(echo)", "a" * 257])
def test_invalid_serial_rejected_before_launch(monkeypatch, serial):
    run = patch_run(monkeypatch)
    with pytest.raises(ValueError):
        AdbClient().tap(serial, 1, 2)
    run.assert_not_called()


@pytest.mark.parametrize("x,y", [(-1, 2), (1.5, 2), (True, 2), (1, 100_001)])
def test_invalid_coordinates_are_not_remote_shell_input(monkeypatch, x, y):
    run = patch_run(monkeypatch)
    with pytest.raises(ValueError):
        AdbClient().tap("phone", x, y)
    run.assert_not_called()


@pytest.mark.parametrize("key", ["HOME;reboot", "ENTER\n", "$(reboot)", "x y", "", "back"])
def test_key_validation(monkeypatch, key):
    run = patch_run(monkeypatch)
    with pytest.raises(ValueError):
        AdbClient().key("phone", key)
    run.assert_not_called()


def test_device_failure_is_explicit(monkeypatch):
    patch_run(monkeypatch, stderr=b"error: device unauthorized.", returncode=1)
    with pytest.raises(DeviceUnavailable, match="unauthorized"):
        AdbClient().tap("phone", 1, 2)


def test_non_device_adb_error(monkeypatch):
    patch_run(monkeypatch, stderr=b"protocol fault", returncode=1)
    with pytest.raises(AdbError, match="protocol fault"):
        AdbClient().devices()


@pytest.mark.parametrize("error,message", [(FileNotFoundError(), "ADB not found"), (subprocess.TimeoutExpired("adb", 4), "timed out")])
def test_launch_failure_and_timeout(monkeypatch, error, message):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(side_effect=error))
    with pytest.raises(AdbError, match=message):
        AdbClient().screenshot("phone")


def test_screenshot_binary_preserved_and_shared(monkeypatch):
    image = png_image()
    patch_run(monkeypatch, image)
    capture = CaptureService(AdbClient())
    frame = capture.capture("phone")
    assert frame.png == image
    assert (frame.serial, frame.width, frame.height) == ("phone", 2, 3)
    assert capture.latest("phone") is frame
    assert capture.latest("other") is None
    capture.forget("phone")
    assert capture.latest("phone") is None


@pytest.mark.parametrize("data", [b"not a PNG", b"\x89PNG\r\n\x1a\n", b"\x89PNG\r\n\x1a\n" + b"a" * 40])
def test_invalid_screenshot_rejected(monkeypatch, data):
    patch_run(monkeypatch, data)
    with pytest.raises(AdbError):
        CaptureService(AdbClient()).capture("phone")


def test_external_scrcpy_lifecycle_and_explicit_serial(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    launch = Mock(return_value=process)
    monkeypatch.setattr("app.streaming.scrcpy.subprocess.Popen", launch)
    scrcpy = ExternalScrcpy()
    scrcpy.start("PHONE2")
    command = launch.call_args.args[0]
    assert command[:4] == ["scrcpy", "--serial", "PHONE2", "--no-audio"]
    assert scrcpy.is_running("PHONE2")
    with pytest.raises(ScrcpyError, match="already running"):
        scrcpy.start("PHONE2")
    scrcpy.close()
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=3)
    assert not scrcpy.is_running("PHONE2")


def test_external_scrcpy_force_stop_only_owned_process(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("scrcpy", 3), None]
    monkeypatch.setattr("app.streaming.scrcpy.subprocess.Popen", Mock(return_value=process))
    scrcpy = ExternalScrcpy()
    scrcpy.start("phone")
    scrcpy.stop("phone")
    process.kill.assert_called_once()
    scrcpy.stop("phone")
    process.terminate.assert_called_once()
