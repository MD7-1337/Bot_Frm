"""Deterministic interactive phone screens shared by GUI and spawned workers.

SQLite serializes short state transitions; pixels are rendered from real state
with OpenCV, not prerecorded success frames. No Qt or ADB is used here.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, replace
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from urllib.parse import quote
from uuid import uuid4

import cv2
import numpy as np

LABEL = "SIMULATED DEVICE — NOT CONNECTED TO ANDROID HARDWARE"
SCENARIOS = {"image": "Basic image click", "wait": "Wait and recognition", "recorder": "Recorded workflow"}
WIDTH, HEIGHT = 360, 720
BUTTON = (60, 480, 240, 64)
MENU_BUTTON = (60, 280, 240, 64)


def is_simulation(serial):
    return isinstance(serial, str) and re.fullmatch(r"sim://[0-9a-f]{32}", serial) is not None


def validate_identity(serial):
    if not is_simulation(serial):
        raise ValueError("Expected an explicit sim:// session identity")
    return serial


def _unavailable(message):
    from app.automation.api.errors import DeviceDisconnected
    return DeviceDisconnected(message)


def initial(scenario="image", delay=2.):
    if scenario not in SCENARIOS or isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= 60 or not math.isfinite(delay):
        raise ValueError("Choose a demo scenario and a finite delay from 0 to 60 seconds")
    return {"scenario": scenario, "delay": float(delay), "deadline": time.monotonic() + delay,
            "screen": "loading" if scenario == "wait" else "start", "scroll": 0, "text": "", "actions": 0}


def resolved(state):
    state = dict(state)
    if state["screen"] == "loading" and time.monotonic() >= state["deadline"]:
        state["screen"] = "reward"
    return state


def _inside(x, y, rectangle):
    left, top, width, height = rectangle
    return left <= x < left + width and top <= y < top + height


def transition(state, command, args):
    state = resolved(state)
    if command == "tap":
        x, y = args
        _coordinates(x, y)
        if _inside(x, y, BUTTON):
            state["screen"] = {"start": "menu" if state["scenario"] == "recorder" else "dashboard",
                               "dashboard": "complete", "reward": "complete", "details": "complete"}.get(state["screen"], state["screen"])
        elif state["screen"] == "menu" and _inside(x, y, MENU_BUTTON):
            state["screen"] = "details"
    elif command == "swipe":
        if len(args) != 5:
            raise ValueError("Swipe requires endpoints and duration")
        x1, y1, x2, y2, milliseconds = args
        _coordinates(x1, y1)
        _coordinates(x2, y2)
        if type(milliseconds) is not int or not 1 <= milliseconds <= 60000:
            raise ValueError("Invalid swipe duration")
        if state["screen"] == "menu" and abs(y2 - y1) >= 30:
            state["scroll"] = int(y2 < y1)
    elif command == "key":
        key, = args
        if key in ("HOME", "KEYCODE_HOME"):
            return initial(state["scenario"], state["delay"])
        if key in ("BACK", "KEYCODE_BACK"):
            state["screen"] = {"details": "menu", "menu": "start", "dashboard": "start", "complete": "start"}.get(state["screen"], state["screen"])
        else:
            from app.automation.api.errors import UnsupportedCapability
            raise UnsupportedCapability("Simulation supports HOME and BACK keys only")
    elif command == "text":
        text, = args
        if not isinstance(text, str) or len(text) > 100 or not text.isascii():
            raise ValueError("Demo text is limited to 100 ASCII characters")
        state["text"] = text
    else:
        raise ValueError("Unsupported simulation command")
    state["actions"] += 1
    return state


def _coordinates(x, y):
    if type(x) is not int or type(y) is not int or not 0 <= x < WIDTH or not 0 <= y < HEIGHT:
        from app.automation.api.errors import InvalidCoordinates
        raise InvalidCoordinates(f"Simulation coordinates must lie within {WIDTH} × {HEIGHT}")


def render(state):
    """Owned uint8 RGB pixels. Stable target crops are identical to screen content."""
    state = resolved(state)
    image = np.full((HEIGHT, WIDTH, 3), (18, 29, 48), np.uint8)
    def text(value, xy, scale=.6, color=(228, 236, 248), thickness=1):
        cv2.putText(image, value, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
    def box(rect, caption, color=(105, 165, 255)):
        x,y,w,h = rect
        cv2.rectangle(image, (x,y), (x+w-1,y+h-1), color, -1)
        cv2.rectangle(image, (x+2,y+2), (x+w-3,y+h-3), (150,195,255), 2)
        size = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, .62, 2)[0]
        text(caption, (x+(w-size[0])//2, y+(h+size[1])//2), .62, (13,29,52), 2)
    text("SIMULATED DEVICE", (26,34), .6, (255,197,101), 2)
    text("NO ANDROID HARDWARE", (26,58), .49, (255,197,101))
    text("09:41    STUDIO DEMO", (26,95), .52)
    screen = state["screen"]
    headings = {"start": "Welcome to Studio", "dashboard": "AUTOMATION READY", "loading": "Preparing reward...",
                "reward": "REWARD READY", "menu": "Your demo tasks", "details": "Review task", "complete": "WORKFLOW COMPLETE"}
    text(headings[screen], (24,160), .73 if screen != "complete" else .66, thickness=2)
    cv2.rectangle(image,(24,205),(335,403),(33,51,76),-1)
    text(SCENARIOS[state["scenario"]], (38,239), .51)
    if screen == "loading":
        progress = 1 if state["delay"] == 0 else max(0., min(1., 1 - (state["deadline"] - time.monotonic()) / state["delay"]))
        cv2.rectangle(image,(40,290),(318,310),(58,76,102),-1)
        cv2.rectangle(image,(40,290),(40+int(278*progress),310),(105,165,255),-1)
        text("Waiting for a real timer", (40,355), .52)
    elif screen == "menu":
        box(MENU_BUTTON, "OPEN TASK B" if state["scroll"] else "OPEN TASK A")
        text("Swipe up to choose task B", (40,380), .5)
    else:
        text({"start":"Capture START as an image.", "dashboard":"Image click changed the state.",
              "reward":"The delayed target is visible.", "details":"Complete the selected task.",
              "complete":"State changed by your actions."}.get(screen,""), (38,290), .48)
        text(state["text"][:27] if state["text"] else "Pixels are generated locally.", (38,330), .48)
    captions = {"start":"START", "dashboard":"CONTINUE", "reward":"CLAIM REWARD", "details":"COMPLETE TASK"}
    if screen in captions:
        box(BUTTON, captions[screen])
    text("Interactive offline simulation", (35,626), .51)
    text("Not USB, ADB or scrcpy video", (35,654), .5)
    text(f"Actions: {state['actions']}", (35,682), .48)
    return image


@dataclass(frozen=True)
class SimulationInfo:
    serial: str
    name: str
    generation: int
    scenario: str
    available: bool = True


class SimulationClient:
    def __init__(self, serial, config):
        self.serial = validate_identity(serial)
        if not isinstance(config, dict) or set(config) != {"database", "token", "generation"}:
            raise ValueError("Simulation requires its explicit session capability")
        if not isinstance(config["database"], str) or not Path(config["database"]).is_absolute() or len(config["database"]) > 4096:
            raise ValueError("Invalid simulation database path")
        if not isinstance(config["token"], str) or re.fullmatch(r"[0-9a-f]{64}", config["token"]) is None:
            raise ValueError("Invalid simulation capability")
        if type(config["generation"]) is not int or config["generation"] < 1:
            raise ValueError("Invalid simulation generation")
        self.config = dict(config)

    def _request(self, command=None, args=()):
        path = Path(self.config["database"])
        if not path.is_file():
            raise _unavailable("Simulation has stopped; start a new demo explicitly")
        try:
            uri = "file:" + quote(path.as_posix(), safe="/:") + "?mode=rw"
            with closing(sqlite3.connect(uri, uri=True, timeout=2)) as connection:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT serial, token, generation, active, state FROM session WHERE id=1").fetchone()
                if not row or row[0] != self.serial or not hmac.compare_digest(row[1], self.config["token"]) or row[2] != self.config["generation"] or not row[3]:
                    raise _unavailable("Simulation connection changed; old contexts cannot resume")
                state = resolved(json.loads(row[4]))
                if command:
                    state = transition(state, command, args)
                connection.execute("UPDATE session SET state=? WHERE id=1", (json.dumps(state, allow_nan=False),))
                connection.commit()
                return state
        except sqlite3.Error as error:
            raise _unavailable(f"Simulation state unavailable: {error}") from error

    def state(self):
        return self._request()

    def capture(self):
        return render(self.state())

    def tap(self, x, y):
        self._request("tap", (x,y))

    def swipe(self, x1,y1,x2,y2,duration_ms=500):
        self._request("swipe", (x1,y1,x2,y2,duration_ms))

    def key(self, key):
        self._request("key", (key,))

    def type_text(self, text):
        self._request("text", (text,))

    def launch_app(self, package):
        from app.automation.api.errors import UnsupportedCapability
        raise UnsupportedCapability("Simulation has no installed Android packages")

    stop_app = launch_app


class SimulationManager:
    def __init__(self, limit=4):
        self._temporary = tempfile.TemporaryDirectory(prefix="aas-simulation-")
        self._records = {}
        self._configs = {}
        self._lock = threading.RLock()
        self.limit = limit

    def create(self, scenario="image", delay=2.):
        state = initial(scenario, delay)
        with self._lock:
            if sum(info.available for info in self._records.values()) >= self.limit:
                raise ValueError("Stop a demo before starting more than four simultaneous sessions")
            identity = uuid4().hex
            serial = "sim://" + identity
            path = Path(self._temporary.name) / (identity + ".sqlite3")
            token = secrets.token_hex(32)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE session(id INTEGER PRIMARY KEY, serial TEXT, token TEXT, generation INTEGER, active INTEGER, state TEXT)")
                connection.execute("INSERT INTO session VALUES(1,?,?,1,1,?)", (serial, token, json.dumps(state)))
                connection.commit()
            self._records[serial] = SimulationInfo(serial, f"Demo {len(self._records)+1}", 1, scenario)
            self._configs[serial] = {"database": str(path), "token": token, "generation": 1}
            return self._records[serial]

    def get(self, serial):
        with self._lock:
            return self._records.get(serial)

    def snapshot(self):
        with self._lock:
            return list(self._records.values())

    def config(self, serial):
        with self._lock:
            info = self._records.get(serial)
            if info is None or not info.available:
                raise _unavailable("Simulation session is not active")
            return dict(self._configs[serial])

    def client(self, serial):
        return SimulationClient(serial, self.config(serial))

    def reset(self, serial, scenario, delay):
        state = initial(scenario, delay)
        with self._lock:
            info = self._records[serial]
            config = self._configs[serial]
            with closing(sqlite3.connect(config["database"], timeout=2)) as connection:
                connection.execute("UPDATE session SET generation=generation+1, active=1, state=? WHERE id=1", (json.dumps(state),))
                connection.commit()
            self._configs[serial] = {**config, "generation": info.generation + 1}
            self._records[serial] = replace(info, generation=info.generation+1, scenario=scenario, available=True)
            return self._records[serial]

    def stop(self, serial):
        with self._lock:
            if serial not in self._records:
                return
            info = self._records[serial]
            with closing(sqlite3.connect(self._configs[serial]["database"], timeout=2)) as connection:
                connection.execute("UPDATE session SET active=0, generation=generation+1 WHERE id=1")
                connection.commit()
            self._records[serial] = replace(info, generation=info.generation+1, available=False)

    def close(self):
        for info in self.snapshot():
            if info.available:
                self.stop(info.serial)
        self._temporary.cleanup()
