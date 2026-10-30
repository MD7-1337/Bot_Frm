"""Connection management fixtures verify actual argv and refusal of global actions."""
import subprocess
from unittest.mock import Mock

import pytest

from app.devices.adb import AdbClient, AdbError, validate_endpoint


@pytest.mark.parametrize("endpoint", ["192.168.1.20:5555", "phone.local:37123", "[2001:db8::2]:43210", "localhost:1", "host:65535"])
def test_valid_explicit_endpoints(endpoint):
    assert validate_endpoint(endpoint) == endpoint


@pytest.mark.parametrize("endpoint", [None, "", "USB123", "host", "host:0", "host:65536", "-a:5555",
    "host:5555;id", "host:5\n", "host name:5", "$(id):5", "x..y:5", "[abcd:]:4", "a-:5", "h:abc", "x" * 256 + ":5"])
def test_unsafe_or_implicit_endpoints_never_start_adb(monkeypatch, endpoint):
    run = Mock()
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    for method in ("connect", "disconnect"):
        with pytest.raises(ValueError):
            getattr(AdbClient(), method)(endpoint)
    with pytest.raises(ValueError):
        AdbClient().pair(endpoint, "123456")
    run.assert_not_called()


@pytest.mark.parametrize("method,extra,output,argv", [
    ("connect", (), b"connected to phone:12345\n", ["connect", "phone:12345"]),
    ("connect", (), b"already connected to phone:12345\n", ["connect", "phone:12345"]),
    ("pair", ("123456",), b"Successfully paired to phone:12345 [guid=adb-one]\n", ["pair", "phone:12345", "123456"]),
    ("disconnect", (), b"disconnected phone:12345\n", ["disconnect", "phone:12345"]),
])
def test_scoped_management_argv_and_acknowledgment(monkeypatch, method, extra, output, argv):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, output, b""))
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    message = getattr(AdbClient(timeout=4), method)("phone:12345", *extra)
    assert "123456" not in message
    assert run.call_args.args[0] == ["adb", *argv]
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["timeout"] == 4


@pytest.mark.parametrize("method,extra", [("connect", ()), ("pair", ("123456",)), ("disconnect", ())])
def test_zero_exit_failure_is_not_connection_success(monkeypatch, method, extra):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=subprocess.CompletedProcess([], 0, b"failed to connect", b"")))
    with pytest.raises(AdbError):
        getattr(AdbClient(), method)("phone:12345", *extra)


@pytest.mark.parametrize("code", ["", "12345", "1234567", "123 45", "a12345", 123456, "123456;echo"])
def test_pair_code_validation_and_redaction(monkeypatch, code):
    run = Mock()
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    with pytest.raises(ValueError):
        AdbClient().pair("phone:12345", code)
    run.assert_not_called()


def test_pair_failure_does_not_echo_code(monkeypatch):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=subprocess.CompletedProcess([], 1, b"", b"bad code 123456")))
    with pytest.raises(AdbError) as error:
        AdbClient().pair("phone:12345", "123456")
    assert "123456" not in str(error.value)
    assert error.value.__suppress_context__


def test_pair_acknowledgment_must_be_the_exact_endpoint(monkeypatch):
    monkeypatch.setattr("app.devices.adb.subprocess.run", Mock(return_value=subprocess.CompletedProcess([], 0, b"Successfully paired to phone:123450", b"")))
    with pytest.raises(AdbError):
        AdbClient().pair("phone:12345", "123456")
