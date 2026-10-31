"""Build and verify the Windows x64 developer portable distribution.

Run on Windows with the repository's Python 3.12 environment and PyInstaller
6.12.0 installed. No cross compilation or installer artifact is claimed here.
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
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD_VERSION = "6.12.0"
PACKAGES = ("PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6", "numpy", "opencv-python-headless", "av", "tzdata")


def write_notices(destination: Path) -> list[dict]:
    """Copy installed distributions' declared license/notice files, with metadata.

    This preserves supplied notices; it is not a license-compatibility verdict.
    QtWebEngine Chromium and actual FFmpeg build obligations need release review.
    """
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    for name in PACKAGES:
        distribution = importlib.metadata.distribution(name)
        record = {"name": name, "version": distribution.version,
                  "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "Review included notices",
                  "notice_files": []}
        for resource in distribution.files or ():
            # RECORD paths can include ../../../Scripts/. Only copy actual
            # license/notice resources into a generated, contained destination.
            if not any(word in resource.name.lower() for word in ("license", "licence", "notice", "copying", "copyright")):
                continue
            source = Path(distribution.locate_file(resource))
            if not source.is_file() or source.stat().st_size > 30_000_000:
                continue
            safe_parts = [part for part in resource.parts if part not in ("", ".", "..", "/", "\\")]
            target = destination / name / Path(*safe_parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            record["notice_files"].append(str(target.relative_to(destination)).replace("\\", "/"))
        inventory.append(record)
    (destination / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    shutil.copyfile(ROOT / "docs" / "THIRD_PARTY_NOTICES.md", destination / "RELEASE_REVIEW.md")
    return inventory


def create_portable_zip(payload: Path, destination: Path) -> str:
    """Archive a generated payload; reject links and write a SHA256 sidecar."""
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite release artifact: {destination}")
    files = sorted(payload.rglob("*"))
    if any(path.is_symlink() for path in files):
        raise ValueError("Portable payload contains symbolic links")
    with tempfile.NamedTemporaryFile(prefix="studio-", suffix=".zip", dir=destination.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                if path.is_file():
                    archive.write(path, Path(payload.name) / path.relative_to(payload))
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-android-tools", action="store_true", help="Include locally reviewed platform-tools/scrcpy artifacts and notices")
    args = parser.parse_args()
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("Build requires a Windows x64 runtime; Linux cannot produce a validated Windows artifact")
    if sys.version_info[:2] != (3, 12):
        parser.error("Build requires Python 3.12")
    if importlib.metadata.version("pyinstaller") != BUILD_VERSION:
        parser.error(f"Install PyInstaller=={BUILD_VERSION} in this environment")
    sys.path.insert(0, str(ROOT))
    from app.editor.assets import validate_monaco
    # The verifier's contract is deliberately honored before the freezer runs.
    validate_monaco(ROOT / "editor_web")
    write_notices(ROOT / "build" / "release-notices")
    env = os.environ.copy()
    env["STUDIO_BUNDLE_ANDROID_TOOLS"] = "1" if args.include_android_tools else "0"
    if args.include_android_tools:
        required = [ROOT / ".tools/platform-tools/adb.exe", ROOT / ".tools/scrcpy-server-v3.1"]
        if not all(path.is_file() for path in required):
            parser.error("Fetch Windows platform-tools and the pinned scrcpy server first")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "packaging/studio.spec")],
                   cwd=ROOT, env=env, check=True)
    payload = ROOT / "dist" / "AndroidAutomationStudio"
    smoke_report = ROOT / "dist" / "windows-frozen-smoke.json"
    subprocess.run([str(payload / "AndroidAutomationStudio.exe"), "--release-smoke-report", str(smoke_report)],
                   cwd=payload, timeout=120, check=True)
    report = json.loads(smoke_report.read_text(encoding="utf-8"))
    if report.get("passed") is not True or report.get("frozen") is not True:
        raise RuntimeError("Frozen Windows GUI/worker smoke did not pass; see windows-frozen-smoke.json")
    version = importlib.metadata.version("android-automation-studio")
    archive = ROOT / "dist" / f"AndroidAutomationStudio-{version}-windows-x64-portable.zip"
    create_portable_zip(payload, archive)
    print(json.dumps({"portable_zip": str(archive), "smoke_report": str(smoke_report), "installer": "not built"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
