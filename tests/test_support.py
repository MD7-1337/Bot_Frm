import json
from pathlib import Path

from app.devices.adb import DeviceInfo
from app.support import bug_report, event_logger, recent_events


def test_bug_report_redacts_serials_and_secrets_without_phone_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ADB_SERVER_SOCKET", "tcp:private-host:5037")
    health = {"checks": [{"name": "ADB", "detail": "device USB_SECRET; token=hidden123; pairing code: 123456"}]}
    report = bug_report(adb_path=str(Path.home() / "tools" / "adb"), health=health,
                        devices=[DeviceInfo("USB_SECRET", "offline", "Pixel")],
                        last_error="ADB error: device 'OTHER_PRIVATE_SERIAL' not found")
    assert "USB_SECRET" not in report
    assert "hidden123" not in report
    assert "123456" not in report
    assert "OTHER_PRIVATE_SERIAL" not in report
    assert str(Path.home()) not in report
    parsed = json.loads(report)
    assert parsed["adb_server_overrides"]["ADB_SERVER_SOCKET"] == "configured"
    assert parsed["device_states"][0]["state"] == "offline"
    assert parsed["connection_diagnostics"].startswith("NOT VERIFIED")
    assert "screenshot" not in parsed and "script_source" not in parsed


def test_application_events_are_bounded_and_kept_local(tmp_path):
    logger, path = event_logger(tmp_path)
    for _ in range(250):
        logger.info("A" * 2000)
    for handler in logger.handlers:
        handler.flush()
    assert path.stat().st_size <= 512_000
    assert len(list((tmp_path / "logs").glob("studio.log*"))) <= 4
    assert len(recent_events(path)) <= 100
