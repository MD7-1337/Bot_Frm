"""Dependency diagnostics without importing Qt or scientific libraries in the caller.

No downloads, server restarts or device commands are performed. The optional
native import probes run in bounded child processes to contain loader failures.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from app.editor.assets import validate_monaco, repair_guidance, PACKAGED_REPAIR
from app.resources import resource_root

DEPENDENCIES = {"PySide6": ("6.8.3", "PySide6.QtWebEngineWidgets"),
                "numpy": ("2.2.4", "numpy"),
                "opencv-python-headless": ("4.11.0.86", "cv2"), "av": ("14.2.0", "av"),
                "tzdata": ("2026.6", "tzdata")}
SERVER_SHA256 = "958f0944a62f23b1f33a16e9eb14844c1a04b882ca175a738c16d23cb22b86c0"


def _detail(error) -> str:
    return str(error).replace(str(Path.home()), "<home>")[:1200]


def dependency_health(*, adb_path: str | None = None, server_path: str | None = None,
                      ocr_path: str | None = None, native: bool = True) -> dict:
    checks = []
    frozen = bool(getattr(sys, 'frozen', False))

    def repair(source, packaged=PACKAGED_REPAIR):
        return packaged if frozen else source

    def add(name, status, detail, repair="", *, required=False):
        checks.append({"name": name, "status": status, "detail": _detail(detail), "repair": repair,
                       "required": required})

    python_ok = sys.version_info[:2] == (3, 12)
    add("Python", "ok" if python_ok else "failed", platform.python_version(),
        repair("Use uv sync --locked --extra test --python 3.12; launch this checkout's .venv Python."), required=True)
    for distribution, (expected, module) in DEPENDENCIES.items():
        try:
            installed = importlib.metadata.version(distribution)
            if installed != expected:
                add(distribution, "failed", f"Installed {installed}; required {expected}", repair("Run uv sync --locked --extra test --python 3.12."), required=True)
                continue
            if native and not getattr(sys, "frozen", False):
                result = subprocess.run([sys.executable, "-c", "import importlib,sys; importlib.import_module(sys.argv[1])", module],
                                        capture_output=True, text=True, timeout=12, check=False)
                if result.returncode:
                    add(distribution, "failed", "Native import failed: " + result.stderr[-1000:],
                        "Check docs/INSTALLATION.md for native Qt libraries. A restricted host may require IT assistance.", required=True)
                    continue
            add(distribution, "ok", installed + ("; native import checked" if native and not getattr(sys, "frozen", False) else "; package metadata checked"), required=True)
        except importlib.metadata.PackageNotFoundError:
            add(distribution, "failed", "Not installed in this Python environment", repair("Run uv sync --locked --extra test --python 3.12."), required=True)
        except (OSError, subprocess.SubprocessError) as error:
            add(distribution, "failed", error, repair("Run this checkout's Python and check available memory/native libraries."), required=True)
    try:
        result = validate_monaco()
        add("Monaco", "ok", f"{result['version']}; {result['files_verified']} pinned files verified", required=True)
    except (OSError, ValueError, RuntimeError) as error:
        add("Monaco", "failed", error, repair_guidance(), required=True)
    try:
        free = shutil.disk_usage(resource_root()).free
        add("Free disk space", "ok" if free >= 1_500_000_000 else "warning",
            f"{free // (1024 * 1024)} MiB free on application volume",
            repair("Allow roughly 1.5 GB for first-time Python/Qt setup plus reusable package cache; select another user-owned volume if needed.",
                   "Extract the complete portable package onto a user-owned volume with enough free space for application and projects."))
    except OSError as error:
        add("Free disk space", "warning", error)

    from app.devices.paths import adb_executable
    effective_adb = adb_executable(adb_path)
    resolved = shutil.which(effective_adb)
    if resolved:
        try:
            result = subprocess.run([resolved, "version"], capture_output=True, text=True, timeout=8, check=False)
            valid = result.returncode == 0 and "Android Debug Bridge version" in result.stdout
            add("ADB", "ok" if valid else "warning", result.stdout[:500] or result.stderr[:500],
                repair("Choose a valid Android SDK platform-tools ADB executable or run python tools/fetch_adb.py.",
                       "Download official Android SDK platform-tools from https://developer.android.com/tools/releases/platform-tools, extract them, and select adb/adb.exe in Settings. Demo Mode needs no ADB."))
        except (OSError, subprocess.SubprocessError) as error:
            add("ADB", "warning", error, "Choose a valid ADB executable; no administrator rights are needed for Demo Mode.")
    else:
        add("ADB", "warning", "Selected ADB executable is missing or not executable",
            repair("Run python tools/fetch_adb.py or set STUDIO_ADB to the executable. ADB is optional for Demo Mode.",
                   "Download official Android SDK platform-tools from https://developer.android.com/tools/releases/platform-tools, extract them, and choose adb/adb.exe in Settings. ADB is optional for Demo Mode."))

    server = Path(os.environ.get("STUDIO_SCRCPY_SERVER") or server_path or resource_root() / ".tools/scrcpy-server-v3.1").expanduser()
    try:
        verified = server.is_file() and server.stat().st_size <= 2_000_000 and hashlib.sha256(server.read_bytes()).hexdigest() == SERVER_SHA256
        add("scrcpy server", "ok" if verified else "warning", "Pinned 3.1 SHA-256 verified" if verified else "3.1 server missing or checksum does not match",
            repair("Run python tools/fetch_scrcpy.py or choose the official matching server. Optional for Demo Mode.",
                   "Choose the official scrcpy 3.1 server from its trusted distribution in Settings; the application verifies its pinned checksum. Optional for Demo Mode."))
    except (OSError, RuntimeError) as error:
        add("scrcpy server", "warning", error, "Choose a readable pinned 3.1 server file.")

    executable = shutil.which(ocr_path or os.environ.get("STUDIO_TESSERACT") or "tesseract")
    if executable:
        try:
            result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=8, check=False)
            valid = result.returncode == 0 and "tesseract" in (result.stdout + result.stderr).lower()
            add("Optional OCR", "ok" if valid else "warning", (result.stdout or result.stderr).splitlines()[0] if result.stdout or result.stderr else "Executable produced no version",
                "Choose a local Tesseract executable in Settings. No engine/models are downloaded automatically.")
        except (OSError, subprocess.SubprocessError) as error:
            add("Optional OCR", "warning", error, "Configure local Tesseract in Settings.")
    else:
        add("Optional OCR", "optional", "Local Tesseract not found; image/color recognition remains available",
            "Install Tesseract using your host's supported method and select it in Settings if OCR is needed.")
    return {"ok": not any(item["required"] and item["status"] == "failed" for item in checks),
            "checks": checks, "physical_android": "NOT VERIFIED", "windows_runtime": "NOT VERIFIED"}


if __name__ == "__main__":
    import json
    report = dependency_health()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 1)
