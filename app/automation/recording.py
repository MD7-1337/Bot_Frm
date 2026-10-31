"""Record acknowledged controls from one connection, never physical phone input."""
from __future__ import annotations

import ast
import base64
import json
from dataclasses import dataclass
import math
from uuid import uuid4

from app.devices.adb import validate_serial, png_dimensions, AdbError
from app.simulation.model import is_simulation, validate_identity


@dataclass(frozen=True)
class RecordingTicket:
    session: str
    epoch: int
    code: str
    duration: float


MAX_SESSION_BYTES = 10_000_000
MAX_EVIDENCE_BYTES = 6_000_000


def image_target_code(code, region, reference):
    """Preserve the recorded tap point inside an explicitly saved crop.

    File existence/texture is verified by the caller before replacing a row.
    This function never saves or executes anything.
    """
    from app.vision.matching import Region
    if not isinstance(region, Region) or not isinstance(reference, str) or not reference:
        raise ValueError("A saved image reference and original crop coordinates are required")
    try:
        tree = ast.parse(code)
        call = tree.body[0].value
        if (len(tree.body) != 1 or not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
                or call.func.id != "tap" or len(call.args) != 2 or call.keywords):
            raise ValueError("Only explicit tap(x, y) calls can be converted")
        x, y = (ast.literal_eval(value) for value in call.args)
        if any(type(value) is not int for value in (x, y)):
            raise ValueError("Tap coordinates must be explicit integers")
    except (SyntaxError, AttributeError, IndexError, TypeError) as error:
        raise ValueError("Select an explicit coordinate tap") from error
    if not (region.x <= x < region.x + region.width and region.y <= y < region.y + region.height):
        raise ValueError("The selected crop must contain the recorded tap point")
    dx, dy = x - region.center.x, y - region.center.y
    argument = json.dumps(reference, ensure_ascii=False)
    if dx or dy:
        argument = f"Pattern({argument}).targetOffset({dx}, {dy})"
    return "click(" + argument + ")"


@dataclass(frozen=True)
class ScreenshotEvidence:
    serial: str
    png: bytes
    size: tuple[int, int]

    def __post_init__(self):
        (validate_identity if is_simulation(self.serial) else validate_serial)(self.serial)
        if not isinstance(self.png,bytes) or len(self.png)>2_000_000:
            raise ValueError("Step screenshot exceeds 2 MB; record a smaller screen or capture a target manually")
        try:
            size=png_dimensions(self.png)
        except AdbError as error:
            raise ValueError("Step screenshot is not a supported PNG") from error
        if size != self.size or size[0]*size[1]>8_500_000:
            raise ValueError("Step screenshot dimensions are invalid or exceed 8.5 MP")


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
        self.evidence: dict[int, ScreenshotEvidence] = {}
        self.durations: dict[int, float] = {}
        self.screen_size = None
        self._session = ""
        self._epoch = 0
        self._last_end = None

    def start(self, serial, generation):
        if self.state != "stopped":
            raise ValueError("Stop the current recording before starting another")
        if not isinstance(serial, str) or not serial or type(generation) is not int or generation < 1:
            raise ValueError("Recording requires a verified device connection")
        (validate_identity if is_simulation(serial) else validate_serial)(serial)
        self.serial, self.generation = serial, generation
        self.actions = []
        self.evidence = {}
        self.durations = {}
        self.screen_size = None
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
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0 <= duration <= 86400 or not math.isfinite(duration):
            raise ValueError("Invalid recorded action duration")
        return RecordingTicket(self._session, self._epoch, code, duration)

    def complete(self, ticket, started, error=None, *, evidence=None):
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
        index=len(self.actions)-1
        self.durations[index]=ticket.duration
        if (isinstance(evidence,ScreenshotEvidence) and evidence.serial == self.serial
                and sum(len(item.png) for item in self.evidence.values()) + len(evidence.png) <= MAX_EVIDENCE_BYTES):
            self.evidence[index]=evidence
            self.screen_size = self.screen_size or evidence.size
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
        header = f"# Recorded controls for device {self.serial}; verify screen geometry before replay.\n"
        source = header + "\n".join(lines) + "\n"
        if len(source.encode("utf-8"))>1_048_576:
            raise ValueError("Generated Python exceeds the worker's 1 MiB source limit")
        compile(source, "<recording>", "exec")
        return source

    def session_json(self) -> str:
        """Portable user-chosen data file; no automatic replay or device reconnection."""
        if self.state != "stopped" or not self.serial:
            raise ValueError("Stop a recording before saving its session")
        self.source()
        screenshots={str(index): {"png":base64.b64encode(item.png).decode("ascii"),"size":list(item.size)} for index,item in self.evidence.items() if index<len(self.actions)}
        payload = json.dumps({"schema_version": 2, "serial": self.serial,
                              "generation": self.generation, "actions": self.actions,
                              "screen_size":self.screen_size,"durations":self.durations,"evidence":screenshots}, ensure_ascii=False, indent=2)
        if len(payload.encode("utf-8")) > MAX_SESSION_BYTES:
            raise ValueError("Recorder session exceeds 10 MB; split the timeline into smaller sessions")
        return payload

    def load_session(self, payload: str):
        if self.state != "stopped":
            raise ValueError("Stop recording before opening a session")
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_SESSION_BYTES:
            raise ValueError("Recorder sessions must be smaller than 10 MB")
        try:
            data = json.loads(payload)
            if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] not in (1,2):
                raise ValueError("Unsupported recorder session version")
            serial = (validate_identity if is_simulation(data["serial"]) else validate_serial)(data["serial"])
            generation = data["generation"]
            if type(generation) is not int or generation < 1:
                raise ValueError("Invalid recorded connection generation")
            actions = data["actions"]
            if not isinstance(actions, list) or len(actions) > self.limit:
                raise ValueError("Recorder session exceeds the timeline limit")
            validated = [self.validate_action(action) for action in actions]
            if len((f"# Recorded controls for device {serial}; verify screen geometry before replay.\n" + "\n".join(validated) + "\n").encode("utf-8")) > 1_048_576:
                raise ValueError("Generated Python exceeds the worker's 1 MiB source limit")
            evidence={}
            durations={}
            size=None
            if data["schema_version"]==2:
                size=data.get("screen_size")
                if size is not None and (not isinstance(size,(list,tuple)) or len(size)!=2 or any(type(x)is not int or not 0<x<=16384 for x in size)):
                    raise ValueError("Invalid recorded screen geometry")
                size=tuple(size) if size else None
                raw_evidence=data.get("evidence",{})
                if not isinstance(raw_evidence,dict) or len(raw_evidence)>self.limit:
                    raise ValueError("Invalid screenshot evidence map")
                for index,item in raw_evidence.items():
                    if not isinstance(index,str) or not index.isdecimal() or not 0<=int(index)<len(actions) or not isinstance(item,dict):
                        raise ValueError("Evidence does not identify a valid timeline step")
                    png=base64.b64decode(item["png"],validate=True)
                    evidence[int(index)]=ScreenshotEvidence(serial,png,tuple(item["size"]))
                if sum(len(item.png) for item in evidence.values())>MAX_EVIDENCE_BYTES:
                    raise ValueError("Recorder screenshot budget exceeded")
                raw_durations=data.get("durations",{})
                if not isinstance(raw_durations,dict):
                    raise ValueError("Invalid duration map")
                for index,duration in raw_durations.items():
                    if not isinstance(index,str) or not index.isdecimal() or not 0<=int(index)<len(actions) or isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0<=duration<=86400 or not math.isfinite(duration):
                        raise ValueError("Invalid recorded duration")
                    durations[int(index)]=duration
        except (KeyError, TypeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("Invalid recorder session data") from error
        # Replace only after all validation; loading data never executes a call.
        self.stop("Loaded session; choose a phone and verify geometry before trusted replay")
        self.serial, self.generation, self.actions = serial, generation, validated
        self.evidence,self.durations,self.screen_size=evidence,durations,size
