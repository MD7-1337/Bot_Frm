"""Create a new user-owned demo project without overwriting existing work."""
from pathlib import Path
import json

import cv2

from app.simulation.model import BUTTON, MENU_BUTTON, initial, render

SOURCES = {
    "image": '# SIMULATED DEVICE — NOT CONNECTED TO ANDROID HARDWARE\nclick("start.png")\nassert exists("continue.png")\nprint("The simulated screen changed after the actual image click.")\n',
    "wait": '# SIMULATED DEVICE — NOT CONNECTED TO ANDROID HARDWARE\n# Home restarts the configured simulation timer.\nhome()\nreward = waitImage("reward.png", timeout=15)\nclick(reward)\nprint("Reward appeared and was claimed in the simulator.")\n',
    "recorder": '# SIMULATED DEVICE — NOT CONNECTED TO ANDROID HARDWARE\nhome()\nclick("start.png")\nswipe(180, 430, 180, 220, duration=0.5)\nclick("task_b.png")\nclick("complete.png")\nprint("Simulated workflow complete.")\n',
}


def create_project(root: Path, identity: str, scenario: str):
    project = Path(root) / ("demo-" + identity.rsplit("/", 1)[-1][:12])
    project.mkdir(parents=True, exist_ok=False)
    (project / "images").mkdir()
    (project / "scripts").mkdir()
    (project / "project.json").write_text(json.dumps({"schema_version": 1, "simulation": True}), encoding="utf-8")
    targets = {"start": ("start", BUTTON, 0), "continue": ("dashboard", BUTTON, 0),
               "reward": ("reward", BUTTON, 0), "task_a": ("menu", MENU_BUTTON, 0),
               "task_b": ("menu", MENU_BUTTON, 1), "complete": ("details", BUTTON, 0)}
    for name, (screen, rectangle, scroll) in targets.items():
        state = {**initial(scenario, 2), "screen": screen, "scroll": scroll}
        image = render(state)
        x,y,w,h = rectangle
        success, data = cv2.imencode(".png", cv2.cvtColor(image[y:y+h,x:x+w], cv2.COLOR_RGB2BGR))
        if not success:
            raise OSError("Could not encode a simulator target")
        (project / "images" / (name + ".png")).write_bytes(data.tobytes())
    for name, source in SOURCES.items():
        (project / "scripts" / (name + ".py")).write_text(source, encoding="utf-8")
    (project / "README.md").write_text("# Offline simulation project\n\nThese are actual templates cropped from locally rendered demo screens. No Android hardware is connected. Reset the matching scenario before running/replaying. Project files are yours; Reset does not overwrite them.\n", encoding="utf-8")
    return project, project / "scripts" / (scenario + ".py")
