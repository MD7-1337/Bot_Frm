"""Frozen entry point. Keep multiprocessing dispatch before any Qt imports."""
from __future__ import annotations

import multiprocessing
import json
from pathlib import Path
import sys


def main() -> int:
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--release-smoke-report":
        from app.release_checks import write_smoke_report
        return write_smoke_report(Path(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "--health-report":
        # Windowed Windows executables have no stdout console. Preserve CLI
        # diagnostics in an explicitly chosen file instead of losing print().
        from app.main import diagnostics
        report = diagnostics()
        target = Path(sys.argv[2])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0 if report["health"]["ok"] else 1
    from app.main import main as studio_main
    return studio_main()


if __name__ == "__main__":
    raise SystemExit(main())
