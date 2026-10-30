#!/usr/bin/env bash
# Linux cloud development setup. Source files and lockfile are never rewritten.
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$studio_root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
uv sync --locked --extra test --python 3.12
.venv/bin/python tools/fetch_monaco.py
.venv/bin/python tools/fetch_adb.py
.venv/bin/python tools/fetch_scrcpy.py
.venv/bin/python -m app.main --diagnostics
