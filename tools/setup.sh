#!/usr/bin/env bash
# Linux cloud development setup. Source files and lockfile are never rewritten.
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$studio_root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"
if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' 'uv is missing. Follow docs/INSTALLATION.md for a user-local install; sudo is not required.' >&2
    exit 1
fi
# A preflight is actionable on storage-constrained school computers. Do not delete caches.
studio_free_kb="$(df -Pk "$studio_root" | awk 'END { print $4 }')"
if [ "${studio_free_kb:-0}" -lt 1500000 ] && [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'Insufficient space for first setup: allow at least 1.5 GB plus cache space. Use another user-owned volume; no files were deleted.' >&2
    exit 1
fi
uv sync --locked --extra test --python 3.12
.venv/bin/python tools/fetch_monaco.py
.venv/bin/python tools/fetch_adb.py
.venv/bin/python tools/fetch_scrcpy.py
.venv/bin/python -m app.main --diagnostics
