"""Exercise both scripting styles in real workers without connected phones.

Run from the checkout: python -m examples.run_visual_fixture
Every image/device is an explicit fixture; this sends no Android commands.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time

import cv2
import numpy as np

from app.automation.runtime import RuntimeCoordinator


def main():
    with tempfile.TemporaryDirectory(prefix="aas-visual-fixture-") as temporary:
        project = Path(temporary)
        (project / "images").mkdir()
        (project / "scripts").mkdir()
        pixels = np.random.default_rng(42).integers(0, 256, (120, 180, 3), dtype=np.uint8)
        frame = project / "fixture-frame.png"
        assert cv2.imwrite(str(frame), cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
        assert cv2.imwrite(str(project / "images/start.png"), cv2.cvtColor(pixels[30:50, 40:60], cv2.COLOR_RGB2BGR))
        actions = []
        with RuntimeCoordinator(max_workers=2) as runtime:
            for serial, example in (("fixture-simple", "visual_script.py"),
                                    ("fixture-explicit", "explicit_device_script.py")):
                source = (Path(__file__).parent / example).read_text(encoding="utf-8")
                script = project / "scripts" / example
                script.write_text(source, encoding="utf-8")
                runtime.start(source, serial, trusted=True, backend="mock", script_id=str(script),
                              project_root=str(project), mock_config={"frame_paths": [str(frame)]})
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                for event in runtime.poll():
                    if event["event"] in ("action", "output", "error"):
                        print(json.dumps(event), flush=True)
                    if event["event"] == "action":
                        actions.append(event)
                if all(run.exitcode is not None for run in runtime.snapshot()):
                    break
                time.sleep(.01)
            else:
                raise TimeoutError("Visual fixture workers did not finish")
            assert all(run.state == "completed" for run in runtime.snapshot()), runtime.snapshot()
            assert {event["serial"] for event in actions} == {"fixture-simple", "fixture-explicit"}
            print("Both visual scripting styles completed in independent mock-device workers.")


if __name__ == "__main__":
    main()
