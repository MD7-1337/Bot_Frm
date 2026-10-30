"""Fetch the pinned, integrity-checked Monaco distribution; no Node runtime needed."""
from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = "https://registry.npmjs.org/monaco-editor/-/monaco-editor-0.52.2.tgz"
INTEGRITY = "GEQWEZmfkOGLdd3XK8ryrfWz3AIP8YymVXiPHEdewrUq7mh0qrKrfHLNCXcbB6sTnMLnOZ3ztSiKcciFUkIJwQ=="


def main() -> None:
    with urllib.request.urlopen(URL, timeout=90) as response:
        data = response.read(40_000_001)
    if len(data) > 40_000_000:
        raise RuntimeError("Monaco archive exceeds download limit")
    if hashlib.sha512(data).digest() != base64.b64decode(INTEGRITY):
        raise RuntimeError("Monaco SHA-512 integrity verification failed")
    destination = ROOT / "editor_web" / "vendor"
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
        if not (staging / "vs/loader.js").is_file():
            raise RuntimeError("Monaco loader missing")
        # Replace only the generated vendor directory after complete verification.
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(staging, destination)
    print("Monaco 0.52.2 verified and installed at", destination)


if __name__ == "__main__":
    main()
