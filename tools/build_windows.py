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
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BUILD_VERSION = "6.12.0"
PACKAGES = ("PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6", "numpy", "opencv-python-headless", "av", "tzdata", "pyinstaller")


def collect_lgpl_notices(destination: Path) -> None:
    """Retain corresponding sources only when they identify the installed wheel."""
    runtime_dir = os.environ.get("STUDIO_LGPL_RUNTIME_DIR")
    if not runtime_dir:
        return  # Developer builds remain blocked from redistribution.
    root = Path(runtime_dir).resolve()
    manifest = json.loads((root / "lgpl-runtime.json").read_text(encoding="utf-8"))
    if manifest.get("source_provenance_complete") is not True or manifest.get("external_prefix") is not False:
        raise ValueError("LGPL runtime has no complete build provenance")
    wheel = Path(manifest["wheel"])
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != manifest["wheel_sha256"]:
        raise ValueError("LGPL runtime wheel differs from its provenance")
    # Compare every installed av native file with that exact repaired wheel.
    distribution = importlib.metadata.distribution("av")
    with zipfile.ZipFile(wheel) as archive:
        native = [name for name in archive.namelist()
                  if name.lower().endswith((".pyd", ".dll", ".so")) or ".so." in name]
        if not native:
            raise ValueError("LGPL wheel has no native libraries")
        for name in native:
            installed = Path(distribution.locate_file(name))
            if not installed.is_file() or hashlib.sha256(installed.read_bytes()).digest() != hashlib.sha256(archive.read(name)).digest():
                raise ValueError("Installed PyAV/FFmpeg differs from verified LGPL wheel: " + name)
    notices = root / "FFmpeg-notices"
    for filename, key in (("ffmpeg-n7.1-source.tar.gz", "ffmpeg_sha256"),
                          ("pyav-14.2.0-source.tar.gz", "pyav_sha256"),
                          ("build_lgpl_runtime.py", "build_script_sha256")):
        if hashlib.sha256((notices / filename).read_bytes()).hexdigest() != manifest[key]:
            raise ValueError("LGPL corresponding source/build script integrity failure")
    shutil.copytree(notices, destination / "FFmpeg", dirs_exist_ok=True)
    shutil.copyfile(root / "lgpl-runtime.json", destination / "FFmpeg" / "lgpl-runtime.json")


def write_payload_inventory(payload: Path, destination: Path) -> dict:
    """Fingerprint actual deployed files; explicitly record unresolved review."""
    records = []
    for path in sorted(payload.rglob("*")):
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(payload.resolve()):
                raise ValueError("Payload inventory link escapes package")
            records.append({"path": path.relative_to(payload).as_posix(), "symlink": os.readlink(path)})
        elif path.is_file() and path != destination:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            records.append({"path": path.relative_to(payload).as_posix(), "bytes": path.stat().st_size, "sha256": digest})
    unexpected_qt = []
    for record in records:
        path = Path(record["path"])
        name = path.name.lower()
        native = name.endswith((".dll", ".pyd", ".dylib", ".so")) or ".so." in name
        modules = ("charts", "datavisualization", "graphs")
        if native and (any(name.startswith(prefix + module) for module in modules
                           for prefix in ("qt", "qt6", "libqt6"))
                       or any(part.lower() in {"qt" + module for module in modules} for part in path.parts)):
            unexpected_qt.append(record["path"])
    report = {"schema": 1, "commit": source_commit(), "platform": platform.platform(),
              "redistribution_approved": False,
              "blockers": ["Application distribution license requires owner decision",
                           "Exact deployed Qt/Chromium source and notice correspondence requires review",
                           "Native dependency license mapping and replacement verification incomplete"],
              "unexpected_gpl_qt_paths": unexpected_qt, "files": records}
    if unexpected_qt:
        report["blockers"].append("Unused GPL-only Qt Charts/DataVisualization/Graphs modules entered the payload")
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if unexpected_qt:
        raise ValueError("Unused GPL-only Qt modules in payload; review retained inventory: " + str(destination))
    return report


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
                  "notice_files": [], "wheel_provenance_files": []}
        for resource in distribution.files or ():
            if resource.name in {"METADATA", "WHEEL", "RECORD"} and any(part.endswith(".dist-info") for part in resource.parts):
                source = Path(distribution.locate_file(resource))
                target = destination / name / "wheel-provenance" / resource.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                record["wheel_provenance_files"].append({
                    "path": target.relative_to(destination).as_posix(),
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
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
        record["notice_status"] = "supplied files retained; review required" if record["notice_files"] else "MISSING: no license/notice text supplied by installed distribution"
        inventory.append(record)
    (destination / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    # CPython's license is outside wheel metadata in common Python layouts.
    for candidate in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if candidate.is_file():
            shutil.copyfile(candidate, destination / "Python-LICENSE.txt")
            break
    collect_lgpl_notices(destination)
    # Query the installed engine rather than assuming wheel and Chromium versions
    # correspond. These calls do not initialize a GUI or start a browser process.
    from PySide6.QtCore import QLibraryInfo
    from PySide6.QtWebEngineCore import qWebEngineChromiumVersion, qWebEngineVersion
    qt_version = QLibraryInfo.version().toString()
    qt_report = {
        "qt_version": qt_version, "qtwebengine_version": qWebEngineVersion(),
        "chromium_version": qWebEngineChromiumVersion(),
        "corresponding_source_verified": False,
        "source_candidates": [
            f"https://download.qt.io/archive/qt/{'.'.join(qt_version.split('.')[:2])}/{qt_version}/submodules/",
            f"https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{importlib.metadata.version('PySide6')}-src/"],
        "review": "Versioned upstream locations are candidates, not verified wheel build/source correspondence or a source offer"}
    (destination / "Qt-build-information.json").write_text(json.dumps(qt_report, indent=2), encoding="utf-8")
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


def source_commit() -> str:
    """Non-secret provenance only; never record the process environment."""
    if value := os.environ.get("GITHUB_SHA"):
        return value
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def write_windows_version(version: str) -> Path:
    """Generate version resources from installed project metadata for this build."""
    parts = tuple(int(part) for part in version.split(".")[:3])
    numbers = (parts + (0, 0, 0, 0))[:4]
    target = ROOT / "build" / "windows-version-info.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=" + repr(numbers) + ", prodvers=" + repr(numbers) +
        ", mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)), "
        "kids=[StringFileInfo([StringTable('040904B0', ["
        "StringStruct('CompanyName', 'MD7-1337'), "
        "StringStruct('FileDescription', 'Android Automation Studio Alpha'), "
        "StringStruct('FileVersion', " + repr(version) + "), "
        "StringStruct('ProductName', 'Android Automation Studio'), "
        "StringStruct('ProductVersion', " + repr(version) + ")])]), "
        "VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n", encoding="utf-8")
    return target


def verify_extracted_zip(archive: Path, report_path: Path) -> dict:
    """Exercise the archive outside the checkout, including relocation/spaces."""
    with tempfile.TemporaryDirectory(prefix="studio extracted Windows ") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as source:
            source.extractall(root)  # This archive was just generated from our payload.
        payload = root / "AndroidAutomationStudio"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        subprocess.run([str(payload / "AndroidAutomationStudio.exe"), "--release-smoke-report", str(report_path)],
                       cwd=root, env=env, timeout=240, check=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("passed") is not True or report.get("frozen") is not True:
        raise RuntimeError("Extracted Windows package did not pass actual frozen smoke")
    return report


def write_checksum(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")
    return digest


def build_installer(version: str) -> Path:
    """Use an existing compatible compiler; never silently install a tool."""
    compiler = shutil.which("ISCC") or shutil.which("iscc")
    if not compiler:
        candidate = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe"
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        raise RuntimeError("Inno Setup 6 compiler not found; install it explicitly or omit --installer")
    subprocess.run([compiler, f"/DAppVersion={version}", str(ROOT / "packaging/studio.iss")], cwd=ROOT, check=True)
    artifact = ROOT / "dist" / "AndroidAutomationStudio-windows-x64-setup.exe"
    if not artifact.is_file():
        raise RuntimeError("Inno compiler did not produce the expected installer artifact")
    write_checksum(artifact)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-android-tools", action="store_true", help="Include locally reviewed platform-tools/scrcpy artifacts and notices")
    parser.add_argument("--installer", action="store_true", help="Compile a per-user installer using an already-installed Inno Setup 6 compiler")
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
    version = importlib.metadata.version("android-automation-studio")
    write_windows_version(version)
    env = os.environ.copy()
    env["STUDIO_BUNDLE_ANDROID_TOOLS"] = "1" if args.include_android_tools else "0"
    if args.include_android_tools:
        required = [ROOT / ".tools/platform-tools/adb.exe", ROOT / ".tools/scrcpy-server-v3.1"]
        if not all(path.is_file() for path in required):
            parser.error("Fetch Windows platform-tools and the pinned scrcpy server first")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "packaging/studio.spec")],
                   cwd=ROOT, env=env, check=True)
    payload = ROOT / "dist" / "AndroidAutomationStudio"
    (payload / "BUILD_INFO.json").write_text(json.dumps({
        "version": version, "commit": source_commit(), "platform": platform.platform(),
        "python": platform.python_version(), "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "Alpha developer review; hardware acceptance pending", "signed": False,
        "android_tools_bundled": args.include_android_tools,
    }, indent=2), encoding="utf-8")
    shutil.copyfile(ROOT / "docs/INSTALL_WINDOWS.md", payload / "START_HERE_WINDOWS.md")
    inventory = ROOT / "dist/windows-payload-inventory.json"
    write_payload_inventory(payload, inventory)
    shutil.copyfile(inventory, payload / "PAYLOAD_INVENTORY.json")
    archive = ROOT / "dist" / "AndroidAutomationStudio-windows-x64-portable.zip"
    digest = create_portable_zip(payload, archive)
    smoke_report = ROOT / "dist" / "windows-frozen-smoke.json"
    report = verify_extracted_zip(archive, smoke_report)
    installer = build_installer(version) if args.installer else None
    manifest = {"version": version, "commit": source_commit(), "portable_zip": archive.name,
                "portable_sha256": digest, "smoke_report": smoke_report.name,
                "smoke_passed": report["passed"], "frozen": report["frozen"],
                "installer": installer.name if installer else None, "signed": False,
                "physical_android": "NOT VERIFIED"}
    (ROOT / "dist/windows-build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
