"""Read-only comparison of two ADB executables in the Studio process environment."""
from __future__ import annotations

import os

from app.devices.adb import AdbClient


def compare_adb(studio_path: str, external_path: str, *, client_factory=AdbClient) -> str:
    rows = ["ADB comparison (same Studio process environment)",
            "adb devices may start or update its shared ADB server when versions differ.",
            "Serials are replaced with labels; no device commands or server resets are requested."]
    for name in ("ADB_SERVER_SOCKET", "ANDROID_ADB_SERVER_PORT", "ADB_SERVER_PORT"):
        rows.append(f"{name}: {'configured' if os.environ.get(name) else 'unset'}")
    serial_labels = {}
    for label, path in (("Studio", studio_path), ("External", external_path)):
        rows.append(f"\n{label} ADB: {path}")
        client = client_factory(path)
        try:
            version = client.version().splitlines()[0]
            rows.append("Version: " + version[:200])
        except Exception as error:
            rows.append("Version: FAIL: " + type(error).__name__ + ": " + str(error)[:300])
            rows.append("Discovery: NOT VERIFIED")
            continue
        try:
            devices = client.devices()
            if not devices:
                rows.append("Discovery: PASS; no devices reported")
            for device in devices:
                serial_labels.setdefault(device.serial, f"[device-{len(serial_labels) + 1}]")
                rows.append(f"{serial_labels[device.serial]}: {device.state}; model={device.model or 'unavailable'}")
        except Exception as error:
            rows.append("Discovery: FAIL: " + type(error).__name__ + ": " + str(error)[:300])
    report = "\n".join(rows)
    for serial in sorted(serial_labels, key=len, reverse=True):
        report = report.replace(serial, serial_labels[serial])
    return report
