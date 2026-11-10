"""Build a Linux x86-64 portable and validate the relocated extracted binary.

Run inside packaging/Dockerfile.ubuntu22, or on an explicitly documented Linux
baseline with Python 3.12 and PyInstaller 6.12.0. No sudo or system changes are
performed by this script. Android tools remain explicitly selected external tools.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "AndroidAutomationStudio-ubuntu-x86_64.tar.gz"


def source_digest(root: Path) -> str:
    """Fingerprint source/resource inputs, independent of checkout timestamps."""
    digest = hashlib.sha256()
    files = []
    for directory in ("app", "editor_web", "packaging", "tools"):
        files.extend(path for path in (root / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts)
    files.extend(root / name for name in ("pyproject.toml", "uv.lock") if (root / name).is_file())
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def create_portable_archive(payload: Path, destination: Path) -> str:
    """Archive only a generated regular tree, preserving executable permissions."""
    if destination.exists():
        raise FileExistsError(f"Refusing to replace release artifact: {destination}")
    files = sorted(payload.rglob("*"))
    if payload.is_symlink():
        raise ValueError("Portable payload root may not be a symbolic link")
    for path in files:
        if path.is_symlink():
            # PyInstaller 6 uses local .so aliases. Keep only internal links;
            # never package a link to source, a venv or another installation.
            target = path.resolve(strict=True)
            if not target.is_relative_to(payload.resolve()) or not target.is_file():
                raise ValueError("Portable payload link escapes the package")
        elif not (path.is_file() or path.is_dir()):
            raise ValueError("Portable payload contains a special file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="studio-portable-", suffix=".tar.gz", dir=destination.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with tarfile.open(temporary_path, "w:gz", compresslevel=6) as archive:
            archive.add(payload, arcname=payload.name, recursive=False)
            for path in files:
                archive.add(path, arcname=str(Path(payload.name) / path.relative_to(payload)), recursive=False)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
    return digest


def extract_generated_archive(archive_path: Path, destination: Path):
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(destination, filter="data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-smoke", action="store_true", help="Build only; does not establish packaged startup acceptance")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("Linux x86-64 is required; Windows is built on a Windows runner")
    if sys.version_info[:2] != (3, 12) or importlib.metadata.version("pyinstaller") != "6.12.0":
        parser.error("Use Python 3.12 and PyInstaller==6.12.0")
    sys.path.insert(0, str(ROOT))
    from app.editor.assets import validate_monaco
    from tools.build_windows import write_notices, write_payload_inventory
    validate_monaco(ROOT / "editor_web")
    write_notices(ROOT / "build/release-notices")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "packaging/linux.spec")], cwd=ROOT, check=True)
    payload = ROOT / "dist/AndroidAutomationStudio"
    launcher = payload / "run-studio.sh"
    launcher.write_text('#!/bin/sh\nset -eu\nstudio_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\nexec "$studio_dir/AndroidAutomationStudio" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    (payload / "README.txt").write_text(
        "Android Automation Studio 0.2.0 Alpha portable\n\nExtract the entire archive and run ./run-studio.sh as your normal desktop user.\n"
        "No system Python, Node.js or virtual environment is needed. Do not run as root.\n"
        "Monaco and Demo Mode work offline. Android tools/OCR are optional external tools selected in Settings.\n"
        "Use --health-report PATH for local diagnostics. Do not disable the browser sandbox for ordinary desktop use.\n"
        "See the included guides for system libraries, USB policy and hardware acceptance.\n", encoding="utf-8")
    guides = payload / "guides"
    guides.mkdir(exist_ok=True)
    for name in ("INSTALL_UBUNTU.md", "REAL_ANDROID_TESTING.md", "HARDWARE_ACCEPTANCE.md",
                 "RELEASE_VALIDATION.md", "REMAINING_ISSUES.md", "KNOWN_ISSUES.md", "SECURITY.md",
                 "SIMULATION.md", "SCRIPTING_API.md", "RECOGNITION.md", "RECORDER.md",
                 "DEBUGGING.md", "RECOVERY.md", "TASKS.md", "PROJECTS.md", "THIRD_PARTY_NOTICES.md"):
        if (ROOT / "docs" / name).is_file():
            shutil.copyfile(ROOT / "docs" / name, guides / name)
    manifest = {"platform": platform.platform(), "glibc": platform.libc_ver(),
                "distribution": platform.freedesktop_os_release(),
                "python": platform.python_version(), "application_version": importlib.metadata.version("android-automation-studio"),
                "pyinstaller": importlib.metadata.version("pyinstaller"),
                "pyinstaller_hooks_contrib": importlib.metadata.version("pyinstaller-hooks-contrib"),
                "source_commit": os.environ.get("STUDIO_BUILD_COMMIT") or os.environ.get("GITHUB_SHA") or "uncommitted-workspace",
                "source_sha256": source_digest(ROOT),
                "frozen": True, "android_hardware": "NOT VERIFIED", "windows": "NOT VERIFIED"}
    (payload / "BUILD_INFO.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    inventory = ROOT / "dist/linux-payload-inventory.json"
    write_payload_inventory(payload, inventory)
    shutil.copyfile(inventory, payload / "PAYLOAD_INVENTORY.json")
    archive = ROOT / "dist" / ARCHIVE
    digest = create_portable_archive(payload, archive)
    if not args.skip_smoke:
        with tempfile.TemporaryDirectory(prefix="studio relocated package with spaces ") as temporary:
            relocated = Path(temporary)
            extract_generated_archive(archive, relocated)
            binary = relocated / payload.name / "AndroidAutomationStudio"
            report_path = ROOT / "dist/linux-frozen-smoke.json"
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            completed = subprocess.run([str(binary), "--release-smoke-report", str(report_path)], cwd=relocated,
                                       env=env, check=False, timeout=180)
            if not report_path.is_file():
                raise RuntimeError(f"Extracted frozen smoke exited {completed.returncode} without a report")
            report = json.loads(report_path.read_text())
            if completed.returncode or not report.get("passed") or report.get("frozen") is not True:
                raise RuntimeError(f"Extracted frozen smoke failed: {json.dumps(report, ensure_ascii=True)}")
    print(json.dumps({"portable_archive": str(archive), "sha256": digest,
                      "smoke": "NOT RUN" if args.skip_smoke else "extracted and relocated frozen executable passed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
