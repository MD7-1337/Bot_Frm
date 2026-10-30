"""Install development platform-tools locally, verified against Google metadata.

Checksums below are from Google's HTTPS repository2-1.xml on 2026-10-29.
Includes Google's license files; release redistribution requires separate review.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import platform
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "Linux": ("linux", "477254aa5f903c15cf51001717bdf347fb6b53e0"),
    "Windows": ("win", "e03e78b1d80b396f1c3358e31251cb31740e1110"),
}


def main():
    if platform.machine().lower() not in ("x86_64", "amd64") or platform.system() not in ARCHIVES:
        raise RuntimeError("This development setup supports x86-64 Linux and Windows only")
    host, expected = ARCHIVES[platform.system()]
    url = f"https://dl.google.com/android/repository/platform-tools_r37.0.1-{host}.zip"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(30_000_001)
    if len(data) > 30_000_000 or hashlib.sha1(data).hexdigest() != expected:
        raise RuntimeError("Platform-tools failed Google's published checksum verification")
    destination = ROOT / ".tools/platform-tools"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts or not member.filename.startswith("platform-tools/"):
                    raise RuntimeError("Unsafe platform-tools archive member")
                archive.extract(member, staging)
        executable = staging / "platform-tools" / ("adb.exe" if host == "win" else "adb")
        if not executable.is_file():
            raise RuntimeError("ADB executable missing")
        if host == "linux":
            executable.chmod(0o755)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(staging / "platform-tools", destination)
    print("Verified platform-tools 37.0.1 installed:", destination)


if __name__ == "__main__":
    main()
