"""Read-only comparison of two ADB executables in the Studio process environment."""
from __future__ import annotations

import os

from app.devices.adb import AdbClient
from app.support import redact


def compare_adb(studio_path: str, external_path: str, *, client_factory=AdbClient) -> str:
    rows = ["ADB comparison (same Studio process environment)",
            "adb devices may start or update its shared ADB server when versions differ.",
            "Serials are replaced with labels; no device commands or server resets are requested."]
    for name in ("ADB_SERVER_SOCKET", "ANDROID_ADB_SERVER_PORT", "ADB_SERVER_PORT"):
        rows.append(f"{name}: {'configured' if os.environ.get(name) else 'unset'}")
    serial_labels = {}
    observed = {}
    for label, path in (("Studio", studio_path), ("External", external_path)):
        rows.append(f"\n{label} ADB: {path}")
        client = client_factory(path)
        try:
            version = client.version().splitlines()[0]
            rows.append("Version: " + version[:200])
        except Exception as error:
            rows.append("Version: FAIL: " + type(error).__name__ + ": " + redact(str(error)[:300], serial_labels))
            rows.append("Discovery: NOT VERIFIED")
            observed[label] = None
            continue
        try:
            devices = client.devices()
            observed[label] = {device.serial: device.state for device in devices}
            if not devices:
                rows.append("Discovery: PASS; no devices reported")
            for device in devices:
                serial_labels.setdefault(device.serial, f"[device-{len(serial_labels) + 1}]")
                rows.append(f"{serial_labels[device.serial]}: {device.state}; model={device.model or 'unavailable'}")
        except Exception as error:
            rows.append("Discovery: FAIL: " + type(error).__name__ + ": " + redact(str(error)[:300], serial_labels))
            observed[label] = None
    studio, external = observed.get("Studio"), observed.get("External")
    if studio is None or external is None:
        advice = "Fix the reported ADB launch or discovery failure, then compare again."
    elif studio == external:
        advice = ("Both ADB listings match. If Studio's Device Manager differs, refresh and export a bug report."
                  if studio else "Neither ADB lists a phone in this process. Check the cable, authorization, driver and how standalone scrcpy was launched.")
    elif any(state == "device" for state in external.values()) and not any(state == "device" for state in studio.values()):
        advice = "The external ADB sees an authorized phone but Studio's ADB does not. Choose the external adb.exe in Studio Settings, refresh, and diagnose again."
    else:
        advice = "The listings differ. Check executable versions and server overrides, then refresh and diagnose the selected phone."
    rows.append("\nNext: " + advice)
    rows.append("ADB may change its shared server during this comparison; repeat discovery after choosing an executable.")
    report = "\n".join(rows)
    for serial in sorted(serial_labels, key=len, reverse=True):
        report = report.replace(serial, serial_labels[serial])
    return report
