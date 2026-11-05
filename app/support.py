"""Bounded, privacy-conscious application events and reviewable bug reports."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import sys

from app.resources import resource_root


def event_logger(data_root: Path) -> tuple[logging.Logger, Path]:
    path = data_root / "logs" / "studio.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("android_automation_studio.events")
    logger.setLevel(logging.INFO)
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = RotatingFileHandler(path, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter('%(asctime)sZ %(levelname)s %(message)s', '%Y-%m-%dT%H:%M:%S'))
    logger.addHandler(handler)
    logger.propagate = False
    return logger, path


def redact(value: str, serials=()) -> str:
    value = str(value).replace(str(Path.home()), "<home>")
    for index, serial in enumerate(sorted(set(serials), key=len, reverse=True), 1):
        if serial:
            value = value.replace(serial, f"[device-{index}]")
    value = re.sub(r"(?i)(\bdevice\s+['\"])[^'\"]+(['\"])", r"\1[REDACTED]\2", value)
    value = re.sub(r"(?i)\b((?:pairing[ _-]?)?code|password|token|secret)\s*[:=]\s*\S+", r"\1=[REDACTED]", value)
    return value


def recent_events(path: Path, *, limit=100) -> list[str]:
    if not path.is_file():
        return []
    # Each rotated file is bounded. Read only the tail of the current file.
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 32_000))
        return stream.read().decode("utf-8", errors="replace").splitlines()[-limit:]


def bug_report(*, adb_path: str, health: dict, devices: list,
               diagnostics=None, log_path: Path | None = None,
               last_error: str | None = None) -> str:
    """Prepare a report for review; never collect screenshots or script source."""
    try:
        version = importlib.metadata.version("android-automation-studio")
    except importlib.metadata.PackageNotFoundError:
        version = "source checkout"
    identity_path = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                     else resource_root()) / "BUILD_INFO.json"
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        identity = {key: identity.get(key) for key in ("version", "commit", "created_utc", "android_tools_bundled")}
    except (OSError, ValueError):
        identity = {"commit": "unavailable in this runtime"}
    serials = [device.serial for device in devices]
    safe_devices = [{"serial": f"[device-{index}]", "state": device.state, "model": device.model}
                    for index, device in enumerate(devices, 1)]
    document = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "app_version": version, "build": identity,
        "platform": platform.platform(), "architecture": platform.machine(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "resource_root": redact(str(resource_root()), serials),
        "effective_adb": redact(adb_path, serials),
        "adb_server_overrides": {name: "configured" if os.environ.get(name) else "unset"
                                 for name in ("ADB_SERVER_SOCKET", "ANDROID_ADB_SERVER_PORT", "ADB_SERVER_PORT")},
        "device_states": safe_devices, "health": health,
        "connection_diagnostics": diagnostics.text(True) if diagnostics else "NOT VERIFIED: run Diagnose Connection",
        "last_discovery_error": last_error or "none recorded in this session",
        "recent_events": recent_events(log_path) if log_path else [],
        "hardware": "NOT VERIFIED by this report",
    }
    def scrub(value):
        if isinstance(value, str):
            return redact(value, serials)
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        return value

    return json.dumps(scrub(document), indent=2, ensure_ascii=False)
