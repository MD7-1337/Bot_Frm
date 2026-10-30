"""Defensive reads for user-editable QSettings values."""

import os
from pathlib import Path


def create_store():
    """Optional per-user portable config directory; no system/registry change required."""
    from PySide6.QtCore import QSettings
    if directory := os.environ.get("STUDIO_CONFIG_DIR"):
        root = Path(directory).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return QSettings(str(root / "studio.ini"), QSettings.Format.IniFormat)
    return QSettings("AndroidAutomationStudio", "Phase0")


def integer(settings, key, default, minimum, maximum):
    try:
        value = int(settings.value(key, default))
    except (ValueError, TypeError, OverflowError):
        return default
    return max(minimum, min(maximum, value))


def theme_name(settings):
    value = settings.value("theme", "dark")
    return value if value in ("dark", "light") else "dark"
