#!/usr/bin/env bash
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$studio_root"
if [ ! -x "$studio_root/.venv/bin/python" ]; then
    printf '%s\n' 'Python environment missing. Follow docs/LOCAL_TESTING.md to run uv sync --locked --extra test --python 3.12.' >&2
    exit 1
fi
exec "$studio_root/.venv/bin/python" -m app.main "$@"
