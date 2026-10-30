from pathlib import Path
import os
import shutil


def adb_executable() -> str:
    """Prefer explicit user configuration, then PATH, then local verified tools."""
    if configured := os.environ.get("STUDIO_ADB"):
        return configured
    if installed := shutil.which("adb"):
        return installed
    local = Path(__file__).resolve().parents[2] / ".tools/platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
    return str(local) if local.is_file() else "adb"
