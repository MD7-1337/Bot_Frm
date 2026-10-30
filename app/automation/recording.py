"""Record acknowledged controls from one connection, never physical phone input."""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
import math
from uuid import uuid4

from app.devices.adb import validate_serial


@dataclass(frozen=True)
class RecordingTicket:
    session: str
    epoch: int
    code: str
    duration: float


class ActionRecorder:
    """A bounded, GUI-owned timeline of successfully completed manual commands.

    Tickets invalidate on pause, stop or a new session, preventing late controls
    from appearing in another recording. A failed/ambiguous action stops capture.
    Replay is ordinary Python through the existing trusted worker path.
    """
    def __init__(self, limit=2000):
        self.limit = limit
        self.serial = None
        self.generation = None
        self.state = "stopped"
        self.reason = "No recording yet"
        self.actions: list[str] = []
        self._session = ""
        self._epoch = 0
        self._last_end = None

    def start(self, serial, generation):
        if self.state != "stopped":
            raise ValueError("Stop the current recording before starting another")
        if not isinstance(serial, str) or not serial or type(generation) is not int or generation < 1:
            raise ValueError("Recording requires a verified device connection")
        validate_serial(serial)
        self.serial, self.generation = serial, generation
        self.actions = []
        self._session = uuid4().hex
        self._epoch += 1
        self._last_end = None
        self.state, self.reason = "recording", "Only completed controls from this studio are recorded"

    def stop(self, reason="Stopped by user"):
        self.state, self.reason = "stopped", reason
        self._epoch += 1
        self._last_end = None

    def pause(self):
        if self.state != "recording":
            raise ValueError("No active recording to pause")
        self.state = "paused"
        self._epoch += 1
        self._last_end = None

    def resume(self, serial, generation):
        if self.state != "paused" or (serial, generation) != (self.serial, self.generation):
            raise ValueError("Resume requires the same recording connection")
        self.state = "recording"
        self._last_end = None

    def ticket(self, serial, generation, code, duration=0.0):
        if self.state != "recording" or (serial, generation) != (self.serial, self.generation):
            return None
        self.validate_action(code)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("Invalid recorded action duration")
        return RecordingTicket(self._session, self._epoch, code, duration)

    def complete(self, ticket, started, error=None):
        if (ticket is None or self.state != "recording" or ticket.session != self._session
                or ticket.epoch != self._epoch):
            return
        if error:
            self.stop("Control failed or completion is uncertain; recording stopped")
            return
        lines = []
        if self._last_end is not None and started - self._last_end >= .05:
            lines.append(f"sleep({min(started - self._last_end, 86400):.3f})")
        lines.append(ticket.code)
        if len(self.actions) + len(lines) > self.limit:
            self.stop(f"Timeline limit ({self.limit} actions) reached")
            return
        self.actions.extend(lines)
        self._last_end = started + ticket.duration

    @staticmethod
    def validate_action(code):
        if not isinstance(code, str) or len(code) > 4096:
            raise ValueError("Each timeline step must be a Python statement under 4096 characters")
        try:
            tree = ast.parse(code)
        except SyntaxError as error:
            raise ValueError(f"Invalid Python step: {error.msg}") from error
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Expr) or not isinstance(tree.body[0].value, ast.Call):
            raise ValueError("Each timeline step must be one Python function call")
        return code.strip()

    def source(self):
        lines = [self.validate_action(line) for line in self.actions]
        header = f"# Recorded controls for ADB serial {self.serial}; verify screen geometry before replay.\n"
        source = header + "\n".join(lines) + "\n"
        compile(source, "<recording>", "exec")
        return source

    def session_json(self) -> str:
        """Portable user-chosen data file; no automatic replay or device reconnection."""
        if self.state != "stopped" or not self.serial:
            raise ValueError("Stop a recording before saving its session")
        self.source()
        payload = json.dumps({"schema_version": 1, "serial": self.serial,
                              "generation": self.generation, "actions": self.actions}, ensure_ascii=False, indent=2)
        if len(payload.encode("utf-8")) > 1_000_000:
            raise ValueError("Recorder session exceeds 1 MB; split the timeline into smaller sessions")
        return payload

    def load_session(self, payload: str):
        if self.state != "stopped":
            raise ValueError("Stop recording before opening a session")
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > 1_000_000:
            raise ValueError("Recorder sessions must be smaller than 1 MB")
        try:
            data = json.loads(payload)
            if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
                raise ValueError("Unsupported recorder session version")
            serial = validate_serial(data["serial"])
            generation = data["generation"]
            if type(generation) is not int or generation < 1:
                raise ValueError("Invalid recorded connection generation")
            actions = data["actions"]
            if not isinstance(actions, list) or len(actions) > self.limit:
                raise ValueError("Recorder session exceeds the timeline limit")
            validated = [self.validate_action(action) for action in actions]
        except (KeyError, TypeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("Invalid recorder session data") from error
        # Replace only after all validation; loading data never executes a call.
        self.stop("Loaded session; choose a phone and verify geometry before trusted replay")
        self.serial, self.generation, self.actions = serial, generation, validated
