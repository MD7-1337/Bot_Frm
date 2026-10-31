"""Measure actual 1/2/4-device spawned simulation workflows; no hardware claim."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.release_checks import simulation_smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"measured_at_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "python": platform.python_version(), "logical_cpus": os.cpu_count(),
              "scope": "short actual worker startup, OpenCV target click and cleanup; not sustained scalability",
              "windows": "NOT VERIFIED" if platform.system() != "Windows" else "Windows runtime",
              "physical_android": "NOT VERIFIED", "runs": []}
    for count in (1, 2, 4):
        with tempfile.TemporaryDirectory(prefix="studio-benchmark-") as temporary:
            report["runs"].append(simulation_smoke(Path(temporary), count=count))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
