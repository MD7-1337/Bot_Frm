from app.devices.adb import DeviceInfo
from app.ui.device_manager import connection_overview


def test_overview_keeps_adb_ready_separate_from_phone_authorization():
    text = connection_overview("C:/Program Files/Android/platform-tools/adb.exe", "ready", [
        DeviceInfo("USB_A", "device", "Pixel"), DeviceInfo("USB_B", "unauthorized")], "USB_B", active_runs=1)
    assert "ADB Ready · 1 accessible · 1 awaiting authorization · 1 active runs · Real Mode" in text
    assert "Effective adb: C:/Program Files/Android/platform-tools/adb.exe" in text
    assert "Selected: USB_B: unauthorized" in text


def test_overview_never_reports_failed_discovery_as_ready():
    text = connection_overview("missing-adb.exe", "failed", [DeviceInfo("USB_A", "unknown")],
                               "USB_A", demo=True, last_error="Could not launch ADB\n  invalid file")
    assert "ADB Unavailable · 0 accessible" in text
    assert "Demo Mode" in text
    assert "Last discovery error: Could not launch ADB invalid file" in text
