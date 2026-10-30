from pathlib import Path
import os
import shutil


def adb_executable(configured: str | None = None) -> str:
    """Environment override, saved user choice, PATH, then local verified tools.

    Explicit invalid paths remain visible errors rather than silently controlling
    a different ADB server. No sudo/administrator operation is attempted.
    """
    if explicit := os.environ.get("STUDIO_ADB") or configured:
        return str(Path(explicit).expanduser())
    if installed := shutil.which("adb"):
        return installed
    local = Path(__file__).resolve().parents[2] / ".tools/platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
    return str(local) if local.is_file() else "adb"
