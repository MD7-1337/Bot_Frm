"""Install the exact scrcpy 3.1 server used by the embedded video client.

Digest published by the upstream release's SHA256SUMS.txt; TLS remains verified.
Only the Android server is needed, not the native scrcpy desktop executable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import urllib.request

URL = "https://github.com/Genymobile/scrcpy/releases/download/v3.1/scrcpy-server-v3.1"
SHA256 = "958f0944a62f23b1f33a16e9eb14844c1a04b882ca175a738c16d23cb22b86c0"


def main():
    target = Path(__file__).resolve().parents[1] / ".tools/scrcpy-server-v3.1"
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == SHA256:
        print("scrcpy 3.1 server already verified:", target)
        return
    with urllib.request.urlopen(URL, timeout=60) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000 or hashlib.sha256(payload).hexdigest() != SHA256:
        raise RuntimeError("scrcpy server SHA-256 verification failed")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".download")
    temporary.write_bytes(payload)
    temporary.replace(target)
    print("scrcpy 3.1 server verified:", target)


if __name__ == "__main__":
    main()
