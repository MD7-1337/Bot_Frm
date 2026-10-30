"""Scripting transport checks use explicit subprocess/image fixtures, not phones."""
from __future__ import annotations

import struct
import subprocess
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from app.automation.api import errors
from app.automation.backends import AdbBackend, MockBackend
from app.devices.adb import AdbClient, AdbError, encode_input_text


def completed(stdout=b"", stderr=b"", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def patch_run(monkeypatch, responses=None, *, stdout=b"", stderr=b"", returncode=0):
    run = Mock(side_effect=responses) if responses is not None else Mock(return_value=completed(stdout, stderr, returncode))
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    return run


def png(rgb):
    ok, data = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return data.tobytes()


def test_capture_decodes_actual_png_into_owned_rgb_and_routes_serial(monkeypatch):
    rgb = np.array([[[210, 15, 80], [20, 190, 35]], [[1, 2, 3], [110, 130, 150]]], dtype=np.uint8)
    run = patch_run(monkeypatch, stdout=png(rgb))
    backend = AdbBackend("fixture-phone-two", "/fixture/platform tools/adb")
    frame = backend.capture()
    assert frame.dtype == np.uint8 and np.array_equal(frame, rgb)
    assert frame.flags.owndata
    assert run.call_args.args[0] == ["/fixture/platform tools/adb", "-s", "fixture-phone-two", "exec-out", "screencap", "-p"]
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize("backend", [AdbBackend, MockBackend])
def test_serial_is_readonly_and_invalid_serial_never_becomes_default(backend):
    bound = backend("fixture-one")
    with pytest.raises(AttributeError):
        bound.serial = "fixture-two"
    for serial in ("", "-d", "phone;reboot", "phone with space"):
        with pytest.raises(ValueError):
            backend(serial)


@pytest.mark.parametrize("detail,exception", [
    (b"error: device unauthorized.", errors.DeviceUnauthorized),
    (b"error: device offline", errors.DeviceOffline),
    (b"error: device 'fixture-one' not found", errors.DeviceDisconnected),
    (b"error: no devices/emulators found", errors.DeviceDisconnected),
    (b"error: no permissions (missing udev rule)", errors.CommandFailed),
    (b"protocol fault", errors.CommandFailed),
])
def test_transport_failures_keep_meaningful_error_types(monkeypatch, detail, exception):
    patch_run(monkeypatch, stderr=detail, returncode=1)
    with pytest.raises(exception):
        AdbBackend("fixture-one").tap(2, 3)


def test_generic_command_failure_is_not_reported_as_device_loss(monkeypatch):
    patch_run(monkeypatch, stderr=b"input command is unsupported", returncode=1)
    with pytest.raises(errors.CommandFailed) as caught:
        AdbBackend("fixture-one").key("HOME")
    assert not isinstance(caught.value, errors.DeviceDisconnected)


def test_transport_deadline_is_command_timeout(monkeypatch):
    patch_run(monkeypatch, responses=subprocess.TimeoutExpired("fixture-adb", 10))
    with pytest.raises(errors.CommandTimeout, match="timed out"):
        AdbBackend("fixture-one").capture()


def test_missing_executable_is_command_failure(monkeypatch):
    patch_run(monkeypatch, responses=FileNotFoundError())
    with pytest.raises(errors.CommandFailed, match="ADB not found"):
        AdbBackend("fixture-one").capture()


@pytest.mark.parametrize("payload", [b"", b"not-an-image", b"\x89PNG\r\n\x1a\n"])
def test_malformed_screenshots_are_frame_errors(monkeypatch, payload):
    patch_run(monkeypatch, stdout=payload)
    with pytest.raises(errors.FrameUnavailable):
        AdbBackend("fixture-one").capture()


def test_touch_and_key_commands_remain_serial_bound(monkeypatch):
    run = patch_run(monkeypatch)
    backend = AdbBackend("fixture-two")
    backend.tap(3, 4)
    backend.swipe(1, 2, 3, 4, duration_ms=900)
    backend.key("KEYCODE_BACK")
    assert [call.args[0] for call in run.call_args_list] == [
        ["adb", "-s", "fixture-two", "shell", "input", "tap", "3", "4"],
        ["adb", "-s", "fixture-two", "shell", "input", "swipe", "1", "2", "3", "4", "900"],
        ["adb", "-s", "fixture-two", "shell", "input", "keyevent", "KEYCODE_BACK"],
    ]


@pytest.mark.parametrize("duration_ms,expected_timeout", [(500, 10), (8000, 10), (12000, 14), (60000, 62)])
def test_gesture_deadline_covers_valid_duration_and_restores_default(monkeypatch, duration_ms, expected_timeout):
    run = patch_run(monkeypatch)
    backend = AdbBackend("fixture-one")
    backend.swipe(1, 2, 3, 4, duration_ms)
    assert run.call_args.kwargs["timeout"] == expected_timeout
    assert backend._adb.timeout == 10
    backend.key("HOME")
    assert run.call_args.kwargs["timeout"] == 10


def test_gesture_deadline_restored_after_transport_error(monkeypatch):
    run = patch_run(monkeypatch, responses=[subprocess.TimeoutExpired("fixture-adb", 62), completed()])
    backend = AdbBackend("fixture-one")
    with pytest.raises(errors.CommandTimeout, match="62"):
        backend.swipe(1, 2, 3, 4, 60000)
    assert run.call_args.kwargs["timeout"] == 62
    assert backend._adb.timeout == 10
    backend.tap(2, 3)
    assert run.call_args.kwargs["timeout"] == 10


@pytest.mark.parametrize("duration_ms", [True, "1000", float("nan"), 0, 60001])
def test_invalid_gesture_duration_is_rejected_before_timeout_change(monkeypatch, duration_ms):
    run = patch_run(monkeypatch)
    backend = AdbBackend("fixture-one")
    with pytest.raises(ValueError):
        backend.swipe(1, 2, 3, 4, duration_ms)
    run.assert_not_called()
    assert backend._adb.timeout == 10


def test_invalid_gesture_coordinates_do_not_change_timeout_or_launch(monkeypatch):
    run = patch_run(monkeypatch)
    backend = AdbBackend("fixture-one")
    with pytest.raises(ValueError, match="coordinates"):
        backend.swipe(-1, 2, 3, 4, 60000)
    run.assert_not_called()
    assert backend._adb.timeout == 10


def test_launch_resolves_one_activity_and_requires_android_confirmation(monkeypatch):
    run = patch_run(monkeypatch, responses=[
        completed(b"priority=0 preferredOrder=0\ncom.example.game/.MainActivity\n"),
        completed(b"Starting: Intent { cmp=com.example.game/.MainActivity }\nStatus: ok\nComplete\n"),
    ])
    AdbBackend("fixture-two").launch_app("com.example.game")
    assert [call.args[0] for call in run.call_args_list] == [
        ["adb", "-s", "fixture-two", "shell", "cmd", "package", "resolve-activity", "--brief", "-a",
         "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "com.example.game"],
        ["adb", "-s", "fixture-two", "shell", "am", "start", "-W", "-n", "com.example.game/.MainActivity"],
    ]


@pytest.mark.parametrize("resolved", [
    b"No activity found\n", b"com.other.app/.MainActivity\n", b"com.example.game/.Main;reboot\n",
    b"com.example.game/.One\ncom.example.game/.Two\n",
])
def test_unresolved_or_untrusted_activity_is_never_launched(monkeypatch, resolved):
    run = patch_run(monkeypatch, stdout=resolved)
    with pytest.raises(errors.CommandFailed, match="resolve"):
        AdbBackend("fixture-one").launch_app("com.example.game")
    assert run.call_count == 1


@pytest.mark.parametrize("output", [
    b"Error: Activity class does not exist\n",
    b"Status: timeout\n", b"Starting: Intent{}\n",
    b"Status: ok\njava.lang.SecurityException: Permission denial\n",
])
def test_zero_exit_code_does_not_fake_launch_success(monkeypatch, output):
    patch_run(monkeypatch, responses=[completed(b"com.example.game/.Main\n"), completed(output)])
    with pytest.raises(errors.CommandFailed):
        AdbBackend("fixture-one").launch_app("com.example.game")


def test_resolve_error_is_not_ignored_beside_an_activity_name(monkeypatch):
    run = patch_run(monkeypatch, stdout=b"com.example.game/.Main\njava.lang.SecurityException: denied\n")
    with pytest.raises(errors.CommandFailed, match="resolve"):
        AdbBackend("fixture-one").launch_app("com.example.game")
    assert run.call_count == 1


def test_stop_checks_package_and_uses_explicit_serial(monkeypatch):
    run = patch_run(monkeypatch, responses=[completed(b"package:/data/app/game/base.apk\n"), completed()])
    AdbBackend("fixture-two").stop_app("com.example.game")
    assert [call.args[0] for call in run.call_args_list] == [
        ["adb", "-s", "fixture-two", "shell", "pm", "path", "com.example.game"],
        ["adb", "-s", "fixture-two", "shell", "am", "force-stop", "com.example.game"],
    ]


def test_missing_package_is_not_reported_as_stopped(monkeypatch):
    run = patch_run(monkeypatch, stdout=b"package not found\n")
    with pytest.raises(errors.CommandFailed, match="not installed"):
        AdbBackend("fixture-one").stop_app("com.example.absent")
    assert run.call_count == 1


def test_package_lookup_exception_is_not_ignored_beside_a_path(monkeypatch):
    run = patch_run(monkeypatch, stdout=b"package:/data/app/game/base.apk\njava.lang.SecurityException: denied\n")
    with pytest.raises(errors.CommandFailed, match="inspect"):
        AdbBackend("fixture-one").stop_app("com.example.game")
    assert run.call_count == 1


@pytest.mark.parametrize("package", ["", "singleword", "com.example;reboot", "com.example.app\n", "$(reboot)", None])
@pytest.mark.parametrize("method", ["launch_app", "stop_app"])
def test_package_injection_rejected_before_any_subprocess(monkeypatch, package, method):
    run = patch_run(monkeypatch)
    with pytest.raises(ValueError):
        getattr(AdbBackend("fixture-one"), method)(package)
    run.assert_not_called()


def test_supported_text_is_encoded_without_remote_shell_fragments(monkeypatch):
    run = patch_run(monkeypatch)
    AdbBackend("fixture-two").type_text("Hello world 123,+-._/@:")
    assert run.call_args.args[0] == ["adb", "-s", "fixture-two", "shell", "input", "text", "Hello%sworld%s123,+-._/@:"]
    run.reset_mock()
    AdbBackend("fixture-two").type_text("")
    run.assert_not_called()


@pytest.mark.parametrize("text", ["téléphone", "📱", "hello;reboot", "a&b", "$(reboot)", "quote'", 'quote"', "literal%s", "a\nb", "a\tb", "a\\b"])
def test_unrepresentable_text_is_explicitly_unsupported_before_io(monkeypatch, text):
    run = patch_run(monkeypatch)
    with pytest.raises(errors.UnsupportedCapability):
        AdbBackend("fixture-one").type_text(text)
    run.assert_not_called()


@pytest.mark.parametrize("text", [None, 123, "a" * 4097])
def test_malformed_text_is_parameter_error(text):
    with pytest.raises(ValueError):
        encode_input_text(text)


@pytest.mark.parametrize("operation", [
    lambda client: client.tap("fixture-one", 1, 2),
    lambda client: client.swipe("fixture-one", 1, 2, 3, 4),
    lambda client: client.key("fixture-one", "HOME"),
    lambda client: client.type_text("fixture-one", "hello"),
])
def test_zero_exit_java_exceptions_are_command_failures(monkeypatch, operation):
    patch_run(monkeypatch, stdout=b"java.lang.IllegalArgumentException: Unsupported input command\n")
    with pytest.raises(AdbError, match="failed"):
        operation(AdbClient())


def test_zero_exit_error_stderr_is_not_success(monkeypatch):
    patch_run(monkeypatch, stderr=b"adb: error: device offline\n")
    with pytest.raises(errors.DeviceOffline):
        AdbBackend("fixture-one").tap(1, 2)


def test_benign_adb_daemon_stderr_is_preserved_as_nonfailure(monkeypatch):
    patch_run(monkeypatch, stdout=b"device\n", stderr=b"* daemon started successfully\n")
    assert AdbClient().state("fixture-one") == "device"


def test_mock_uses_actual_png_frames_in_sequence_then_repeats_final(tmp_path):
    red = np.full((4, 5, 3), (210, 11, 25), dtype=np.uint8)
    green = np.full((4, 5, 3), (12, 190, 35), dtype=np.uint8)
    paths = [tmp_path / "one.png", tmp_path / "téléphone.png"]
    paths[0].write_bytes(png(red))
    paths[1].write_bytes(png(green))
    config = {"frame_paths": list(map(str, paths))}
    one = MockBackend("fixture-one", config)
    two = MockBackend("fixture-two", config)
    assert np.array_equal(one.capture(), red)
    assert np.array_equal(one.capture(), green)
    final = one.capture()
    assert np.array_equal(final, green)
    final[:] = 0
    assert np.array_equal(one.capture(), green), "Caller mutation changed a later fixture capture"
    assert np.array_equal(two.capture(), red), "Two devices shared a capture index"
    config["frame_paths"].clear()
    assert np.array_equal(two.capture(), green), "Caller config mutation changed the active backend"


def test_mock_default_and_configured_resolution():
    assert MockBackend("fixture-one").capture().shape == (1920, 1080, 3)
    assert MockBackend("fixture-two", {"resolution": [11, 7]}).capture().shape == (7, 11, 3)


def test_mock_disconnection_is_not_a_successful_noop():
    backend = MockBackend("fixture-one", {"resolution": [3, 2], "disconnect_after": 1})
    backend.tap(1, 1)
    backend.capture()
    for operation in (backend.capture, lambda: backend.tap(1, 1), lambda: backend.key("HOME"),
                      lambda: backend.swipe(0, 0, 1, 1), lambda: backend.launch_app("com.example.app"),
                      lambda: backend.stop_app("com.example.app"), lambda: backend.type_text("hello")):
        with pytest.raises(errors.DeviceDisconnected):
            operation()


@pytest.mark.parametrize("config", [
    [], {"unknown": True}, {"resolution": [0, 2]}, {"resolution": [True, 2]},
    {"resolution": [20000, 2]}, {"resolution": [16384, 16384]}, {"frame_paths": "image.png"},
    {"frame_paths": [""]}, {"frame_paths": ["bad\x00path.png"]}, {"frame_paths": [None]},
    {"disconnect_after": True}, {"disconnect_after": -1}, {"disconnect_after": float("nan")},
])
def test_mock_configuration_is_bounded_and_explicit(config):
    with pytest.raises(ValueError):
        MockBackend("fixture-one", config)


def test_mock_missing_and_malformed_pngs_are_frame_errors(tmp_path):
    missing = tmp_path / "missing.png"
    with pytest.raises(errors.FrameUnavailable):
        MockBackend("fixture-one", {"frame_paths": [str(missing)]}).capture()
    malformed = tmp_path / "malformed.png"
    malformed.write_bytes(b"not a PNG")
    with pytest.raises(errors.FrameUnavailable):
        MockBackend("fixture-one", {"frame_paths": [str(malformed)]}).capture()


def test_png_header_checked_before_native_decode(tmp_path, monkeypatch):
    huge = tmp_path / "too-large.png"
    huge.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 16384, 16384) + b"\x08\x02\x00\x00\x00" + b"\0" * 4)
    decode = Mock()
    monkeypatch.setattr("app.automation.backends.cv2.imdecode", decode)
    with pytest.raises(errors.FrameUnavailable, match="dimensions"):
        MockBackend("fixture-one", {"frame_paths": [str(huge)]}).capture()
    decode.assert_not_called()
