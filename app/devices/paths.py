from pathlib import Path
import os
import shutil
import sys
from app.resources import resource_root


def adb_executable(configured: str | None = None) -> str:
    """Environment override, saved user choice, portable tools, SDK, then PATH.

    Explicit invalid paths remain visible errors rather than silently controlling
    a different ADB server. No sudo/administrator operation is attempted.
    """
    if explicit := os.environ.get("STUDIO_ADB") or configured:
        return str(Path(explicit).expanduser())
    name = "adb.exe" if sys.platform == "win32" else "adb"
    candidates = [resource_root() / ".tools/platform-tools" / name]
    if getattr(sys, "frozen", False):
        # PyInstaller onedir resources live in _internal; user-supplied portable
        # platform-tools may instead sit alongside the EXE (or one level up).
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend((exe_dir / "platform-tools" / name,
                           exe_dir / name,
                           exe_dir.parent / "platform-tools" / name))
    if sys.platform == "win32":
        for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            if root := os.environ.get(variable):
                candidates.append(Path(root) / "platform-tools" / name)
        if local_app_data := os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(local_app_data) / "Android/Sdk/platform-tools" / name)
        if scrcpy := shutil.which("scrcpy.exe"):
            candidates.append(Path(scrcpy).parent / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or name
