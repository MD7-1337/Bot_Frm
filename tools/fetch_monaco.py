"""Fetch the pinned, integrity-checked Monaco distribution; no Node runtime needed."""
from __future__ import annotations

import base64
import hashlib
import io
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request
from uuid import uuid4
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.editor.assets import MonacoAssetsError, validate_monaco
URL = "https://registry.npmjs.org/monaco-editor/-/monaco-editor-0.52.2.tgz"
INTEGRITY = "GEQWEZmfkOGLdd3XK8ryrfWz3AIP8YymVXiPHEdewrUq7mh0qrKrfHLNCXcbB6sTnMLnOZ3ztSiKcciFUkIJwQ=="


def main() -> None:
    destination = ROOT / "editor_web" / "vendor"
    if destination.is_symlink() or destination.parent.is_symlink():
        raise RuntimeError("Refusing to replace symbolic-linked Monaco assets. Choose this checkout's real editor_web/vendor directory; preserve unrelated files.")
    try:
        validate_monaco(ROOT / "editor_web")
    except (MonacoAssetsError, OSError, ValueError):
        pass
    else:
        print("Monaco 0.52.2: all pinned local assets already verified")
        return
    if shutil.disk_usage(ROOT).free < 100_000_000:
        raise RuntimeError("Not enough free disk space for Monaco setup (100 MB required for download and atomic replacement). Select another user-owned volume; no files were removed.")
    cache = Path(os.environ.get("STUDIO_DOWNLOAD_CACHE") or ROOT / ".tools/download-cache").expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / "monaco-editor-0.52.2.tgz"
    data = cached.read_bytes() if cached.is_file() and cached.stat().st_size <= 40_000_000 else b""
    if hashlib.sha512(data).digest() != base64.b64decode(INTEGRITY):
        with urllib.request.urlopen(URL, timeout=90) as response:
            data = response.read(40_000_001)
    if len(data) > 40_000_000:
        raise RuntimeError("Monaco archive exceeds download limit")
    if hashlib.sha512(data).digest() != base64.b64decode(INTEGRITY):
        raise RuntimeError("Monaco SHA-512 integrity verification failed")
    temporary_cache = cached.with_name(cached.name + "." + uuid4().hex + ".tmp")
    try:
        temporary_cache.write_bytes(data)
        temporary_cache.replace(cached)
    finally:
        temporary_cache.unlink(missing_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive:
                path = Path(member.name)
                if not member.isfile():
                    continue
                if member.name.startswith("package/min/vs/"):
                    relative = Path(*path.parts[2:])
                elif member.name in ("package/LICENSE", "package/ThirdPartyNotices.txt"):
                    relative = Path(path.name)
                else:
                    continue
                if ".." in relative.parts or relative.is_absolute():
                    raise RuntimeError("Unsafe archive member")
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError("Unreadable archive member")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        # Validate all known distribution files before moving the old installation.
        verification_root = staging / "verify"
        verification_root.mkdir()
        ready = verification_root / "vendor"
        ready.mkdir()
        for child in list(staging.iterdir()):
            if child != verification_root:
                child.rename(ready / child.name)
        validate_monaco(verification_root)
        previous = destination.with_name(".vendor-backup-" + uuid4().hex)
        moved = False
        try:
            if destination.exists():
                destination.rename(previous)
                moved = True
            ready.rename(destination)
        except OSError:
            if moved and not destination.exists():
                previous.rename(destination)
            raise
        else:
            if moved:
                shutil.rmtree(previous)
    print("Monaco 0.52.2 verified and installed at", destination)


if __name__ == "__main__":
    main()
