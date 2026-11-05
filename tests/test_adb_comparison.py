from app.devices.adb import DeviceInfo
from app.devices.comparison import compare_adb


def test_comparison_shows_different_discovery_with_stable_redaction(monkeypatch):
    monkeypatch.setenv("ADB_SERVER_SOCKET", "tcp:private:5037")

    class Client:
        def __init__(self, path):
            self.path = path

        def version(self):
            return "Android Debug Bridge version 1.0.41\nBuild details"

        def devices(self):
            return [] if self.path == "studio-adb" else [DeviceInfo("PRIVATE_SERIAL", "device", "Pixel")]

    report = compare_adb("studio-adb", "external-adb", client_factory=Client)
    assert "Studio ADB: studio-adb" in report
    assert "External ADB: external-adb" in report
    assert "no devices reported" in report
    assert "[device-1]: device" in report
    assert "PRIVATE_SERIAL" not in report
    assert "tcp:private:5037" not in report


def test_comparison_reports_individual_launch_failure():
    class Client:
        def __init__(self, path):
            self.path = path

        def version(self):
            if self.path == "broken":
                raise OSError("file missing")
            return "Android Debug Bridge version 1.0.41"

        def devices(self):
            return []

    report = compare_adb("broken", "working", client_factory=Client)
    assert "Version: FAIL: OSError: file missing" in report
    assert "External ADB: working" in report
    assert "Discovery: PASS; no devices reported" in report
