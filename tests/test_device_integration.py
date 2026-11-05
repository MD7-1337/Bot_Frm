"""Deterministic device-state/control tests; all phone serials are fixtures."""
from __future__ import annotations

import struct
import subprocess
import threading
from unittest.mock import Mock

import pytest

from app.devices.adb import (AdbClient, AdbError, DeviceInfo, DeviceOffline,
                             DevicePermissionDenied, DeviceUnauthorized,
                             DeviceUnavailable, ScreenInfo, parse_orientation)
from app.devices.registry import DeviceRegistry


def png_header(width=1080, height=2400):
    # Header fixture only: this is used for adapter dimensions, not a render test.
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00" + b"\x00" * 4


def completed(stdout=b"", stderr=b"", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_registry_disconnect_reconnect_generations_and_model_preservation():
    registry = DeviceRegistry()
    first = registry.update([DeviceInfo("USB_A", "device", "Pixel"), DeviceInfo("USB_B", "offline")])
    assert [record.generation for record in first] == [1, 1]
    registry.update([DeviceInfo("USB_A", "device"), DeviceInfo("USB_B", "unauthorized")])
    assert registry.get("USB_A") == DeviceInfo("USB_A", "device", "Pixel", 1)
    assert registry.get("USB_B").generation == 2
    registry.update([DeviceInfo("USB_B", "device")])
    assert registry.get("USB_A") == DeviceInfo("USB_A", "disconnected", "Pixel", 2)
    assert registry.get("USB_B").available
    registry.update([DeviceInfo("USB_A", "device"), DeviceInfo("USB_B", "device")])
    assert registry.get("USB_A") == DeviceInfo("USB_A", "device", "Pixel", 3)
    assert registry.get("USB_B").generation == 3
    assert registry.get("UNSEEN") is None


def test_discovery_failure_means_unknown_not_disconnected():
    registry = DeviceRegistry()
    registry.update([DeviceInfo("USB_A", "device", "Known")])
    assert registry.mark_unknown() == [DeviceInfo("USB_A", "unknown", "Known", 2)]
    assert registry.mark_unknown()[0].generation == 2
    assert not registry.get("USB_A").available
    assert registry.update([]) == [DeviceInfo("USB_A", "disconnected", "Known", 3)]


def test_adb_discovery_states_flow_into_registry():
    registry = DeviceRegistry()
    connected = AdbClient.parse_devices("List of devices attached\r\nPHONE device model:Pixel_8\r\n")
    assert registry.update(connected) == [DeviceInfo("PHONE", "device", "Pixel_8", 1)]
    unauthorized = AdbClient.parse_devices("List of devices attached\nPHONE unauthorized\n")
    assert registry.update(unauthorized) == [DeviceInfo("PHONE", "unauthorized", "Pixel_8", 2)]
    offline = AdbClient.parse_devices("List of devices attached\nPHONE offline\n")
    assert registry.update(offline) == [DeviceInfo("PHONE", "offline", "Pixel_8", 3)]
    assert registry.update(AdbClient.parse_devices("List of devices attached\n")) == [
        DeviceInfo("PHONE", "disconnected", "Pixel_8", 4)]
    assert registry.update(connected) == [DeviceInfo("PHONE", "device", "Pixel_8", 5)]


def test_snapshot_is_an_independent_container():
    registry = DeviceRegistry()
    result = registry.update([DeviceInfo("USB_A", "device")])
    result.clear()
    snapshot = registry.snapshot()
    snapshot.clear()
    assert len(registry.snapshot()) == 1


def test_invalid_snapshot_preserves_existing_state():
    registry = DeviceRegistry()
    registry.update([DeviceInfo("USB_A", "device")])
    with pytest.raises(ValueError, match="Duplicate"):
        registry.update([DeviceInfo("USB_B", "device"), DeviceInfo("USB_B", "offline")])
    assert registry.snapshot() == [DeviceInfo("USB_A", "device", generation=1)]


@pytest.mark.parametrize("output,expected", [
    (b"List of devices attached\n", []),
    (b"List of devices attached\nA device\nB offline\nC unauthorized\nD authorizing\nE connecting\nF rescue\nG no permissions (no access)\nH new-future-state\n",
     [("A", "device"), ("B", "offline"), ("C", "unauthorized"), ("D", "authorizing"), ("E", "connecting"), ("F", "rescue"), ("G", "no permissions"), ("H", "unknown")]),
])
def test_full_device_state_listing(monkeypatch, output, expected):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=completed(output)))
    assert [(item.serial, item.state) for item in AdbClient().devices()] == expected


@pytest.mark.parametrize("output,message", [
    (b"Unexpected transport response\n", "header"),
    (b"List of devices attached\nA device\nA offline\n", "duplicate"),
    (b"List of devices attached\nBROKEN_ROW\n", "malformed"),
    (b"List of devices attached\nadb: server unreachable\n", "malformed"),
    (b"List of devices attached\nINVALID! device\n", "invalid device identifier"),
])
def test_ambiguous_discovery_is_an_error_not_an_empty_list(monkeypatch, output, message):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=completed(output)))
    with pytest.raises(AdbError, match=message):
        AdbClient().devices()


def test_discovery_does_not_interpret_bootstrap_logs_as_phones(monkeypatch):
    output = b"adb server version (41) does not match client\n* daemon started successfully\nList of devices attached\nUSB_A device\n"
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=completed(output)))
    assert AdbClient().devices() == [DeviceInfo("USB_A", "device")]


def test_missing_android_command_is_not_reported_as_a_disconnected_phone(monkeypatch):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=completed(stderr=b"/system/bin/sh: dumpsys: not found", returncode=1)))
    assert AdbClient().orientation("USB_A") is None


@pytest.mark.parametrize("detail,exception,state", [
    (b"error: device unauthorized.", DeviceUnauthorized, "unauthorized"),
    (b"error: device offline", DeviceOffline, "offline"),
    (b"error: device 'USB_A' not found", DeviceUnavailable, "disconnected"),
    (b"error: no devices/emulators found", DeviceUnavailable, "disconnected"),
    (b"error: no permissions (missing udev rule)", DevicePermissionDenied, "no permissions"),
])
def test_error_types_and_get_state(monkeypatch, detail, exception, state):
    run = Mock(return_value=completed(stderr=detail, returncode=1))
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    client = AdbClient()
    with pytest.raises(exception):
        client.tap("USB_A", 1, 2)
    assert client.state("USB_A") == state
    assert run.call_args.args[0] == ["adb", "-s", "USB_A", "get-state"]


def test_get_state_success_unknown_and_transport_failure(monkeypatch):
    run = Mock(side_effect=[completed(b"device\n"), completed(b"not-a-known-state"), completed(stderr=b"protocol fault", returncode=1)])
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    client = AdbClient()
    assert client.state("USB_A") == "device"
    assert client.state("USB_B") == "unknown"
    with pytest.raises(AdbError, match="protocol fault"):
        client.state("USB_A")


@pytest.mark.parametrize("output,rotation", [
    ("SurfaceOrientation: 0", 0), ("SurfaceOrientation: 1", 90),
    ("SurfaceOrientation: 2", 180), ("SurfaceOrientation: 3", 270),
    ("mCurrentRotation=ROTATION_90", 90),
    ("mCurrentRotation=ROTATION_270", 270),
    ("Viewport INTERNAL: displayId=0, orientation=2", 180),
    ("Viewport EXTERNAL: displayId=1, orientation=3", None),
    ("SurfaceOrientation: 4", None), ("Physical size: 1080x2400", None),
    ("", None),
])
def test_only_observed_orientation_is_reported(output, rotation):
    assert parse_orientation(output) == rotation


def test_current_png_dimensions_take_precedence_over_natural_display_shape(monkeypatch):
    run = Mock(side_effect=[completed(png_header(2400, 1080)), completed(b"SurfaceOrientation: 1\n")])
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    assert AdbClient().screen_info("USB_B") == ScreenInfo(2400, 1080, 90)
    assert [call.args[0] for call in run.call_args_list] == [
        ["adb", "-s", "USB_B", "exec-out", "screencap", "-p"],
        ["adb", "-s", "USB_B", "shell", "dumpsys", "input"],
    ]


def test_orientation_unsupported_and_disconnect_are_distinct(monkeypatch):
    run = Mock(side_effect=[completed(stderr=b"dumpsys permission denied", returncode=1), completed(stderr=b"device offline", returncode=1)])
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    client = AdbClient()
    assert client.orientation("USB_A") is None
    with pytest.raises(DeviceOffline):
        client.orientation("USB_A")


@pytest.mark.parametrize("width,height", [(0, 1), (1, 0), (16385, 1), (16384, 16384)])
def test_malformed_screenshot_dimensions_rejected(monkeypatch, width, height):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=completed(png_header(width, height))))
    with pytest.raises(AdbError, match="dimensions"):
        AdbClient().resolution("USB_A")


def test_double_tap_long_press_and_drag_route_selected_device(monkeypatch):
    run = Mock(return_value=completed())
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    sleep = Mock()
    monkeypatch.setattr("app.devices.adb.time.sleep", sleep)
    client = AdbClient()
    client.double_tap("USB_B", 10, 20, interval=0.1)
    client.long_press("USB_A", 30, 40, duration_ms=1000)
    client.drag("USB_B", 1, 2, 3, 4, duration_ms=600)
    sleep.assert_called_once_with(0.1)
    assert [call.args[0] for call in run.call_args_list] == [
        ["adb", "-s", "USB_B", "shell", "input", "tap", "10", "20"],
        ["adb", "-s", "USB_B", "shell", "input", "tap", "10", "20"],
        ["adb", "-s", "USB_A", "shell", "input", "swipe", "30", "40", "30", "40", "1000"],
        ["adb", "-s", "USB_B", "shell", "input", "swipe", "1", "2", "3", "4", "600"],
    ]


def test_double_tap_serializes_both_taps_but_not_other_devices(monkeypatch):
    run = Mock(return_value=completed())
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    delay_started = threading.Event()
    release = threading.Event()
    errors = []

    def hold(seconds):
        delay_started.set()
        assert release.wait(2)

    monkeypatch.setattr("app.devices.adb.time.sleep", hold)
    client = AdbClient()

    def execute(operation):
        try:
            operation()
        except BaseException as error:
            errors.append(error)

    double = threading.Thread(target=execute, args=(lambda: client.double_tap("USB_A", 1, 2),))
    other_action = threading.Thread(target=execute, args=(lambda: client.key("USB_A", "HOME"),))
    double.start()
    assert delay_started.wait(2)
    other_action.start()
    client.key("USB_B", "BACK")
    release.set()
    double.join(2)
    other_action.join(2)
    assert not errors and not double.is_alive() and not other_action.is_alive()
    calls = [call.args[0] for call in run.call_args_list]
    assert calls[0][1:3] == ["-s", "USB_A"]
    assert calls[1][1:3] == ["-s", "USB_B"]
    assert calls[2][-4:] == ["input", "tap", "1", "2"]
    assert calls[3][-2:] == ["keyevent", "HOME"]


@pytest.mark.parametrize("interval", [float("nan"), float("inf"), -0.1, 1.01, True, "0.2"])
def test_invalid_double_tap_does_not_launch(monkeypatch, interval):
    run = Mock()
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    with pytest.raises(ValueError):
        AdbClient().double_tap("USB_A", 1, 2, interval)
    run.assert_not_called()


@pytest.mark.parametrize("timeout", [True, "10", None, float("nan")])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValueError):
        AdbClient(timeout=timeout)
