"""Worker-local stdlib bdb debugger over bounded private JSON pipes.

The host approves ordinary Python execution; this is not a sandbox. Inspection
intentionally never calls arbitrary repr/property/eval hooks. No TCP endpoint is
created, and frames remain exclusively in their owning worker.
"""
from __future__ import annotations

import bdb
import hashlib
import json
from typing import Any

from app.automation.api.errors import Cancelled

MAX_BREAKPOINTS = 200
MAX_COMMAND_BYTES = 3072
COMMANDS = frozenset({"continue", "pause", "step_into", "step_over", "step_out",
                      "set_breakpoints", "inspect"})


def validate_breakpoints(lines, source: str | None = None) -> list[int]:
    if not isinstance(lines, (list, tuple)) or len(lines) > MAX_BREAKPOINTS:
        raise ValueError("Breakpoints must be a list of at most 200 line numbers")
    maximum = len(source.splitlines()) if source is not None else 1_000_000
    if any(type(line) is not int or not 1 <= line <= maximum for line in lines):
        raise ValueError("Breakpoint lines must refer to the approved source snapshot")
    return sorted(set(lines))


def command_bytes(command: str, payload: dict) -> bytes:
    if command not in COMMANDS:
        raise ValueError("Unsupported debug command")
    if command == "set_breakpoints":
        if set(payload) != {"lines"}:
            raise ValueError("set_breakpoints requires lines")
        payload = {"lines": validate_breakpoints(payload["lines"])}
    elif command == "inspect":
        if set(payload) != {"frame_index"} or type(payload["frame_index"]) is not int or not 0 <= payload["frame_index"] < 20:
            raise ValueError("Frame index must be between 0 and 19")
    elif payload:
        raise ValueError("Debug command does not accept arguments")
    data = json.dumps({"command": command, **payload}, ensure_ascii=True).encode("utf-8")
    if len(data) > MAX_COMMAND_BYTES:
        raise ValueError("Debug command exceeds size limit")
    return data


def type_name(kind: type) -> str:
    # type.__getattribute__ still invokes descriptors on a custom metaclass.
    # Read CPython's actual name slot directly, bypassing user-defined hooks.
    return type.__dict__["__name__"].__get__(kind)


def safe_value(value: Any, depth: int = 0) -> str:
    """Bound primitive display without executing user-defined repr methods."""
    kind = type(value)
    if kind in (type(None), bool, float):
        return repr(value)
    if kind is int:
        return repr(value) if value.bit_length() < 1024 else "<large integer>"
    if kind in (str, bytes):
        return repr(value[:160]) + ("…" if len(value) > 160 else "")
    if depth < 2 and kind in (tuple, list):
        left, right = ("[", "]") if kind is list else ("(", ")")
        return (left + ", ".join(safe_value(item, depth + 1) for item in value[:6]) +
                (", …" if len(value) > 6 else "") + right)[:240]
    if depth < 2 and kind is dict:
        entries = []
        for index, (key, item) in enumerate(value.items()):
            if index == 6:
                entries.append("…")
                break
            entries.append(safe_value(key, depth + 1) + ": " + safe_value(item, depth + 1))
        return ("{" + ", ".join(entries) + "}")[:240]
    return "<" + type_name(kind)[:100] + " object>"


def variables(mapping, baseline=None) -> list[dict]:
    baseline = baseline or {}
    names = sorted(name for name in mapping if type(name) is str and not name.startswith("__")
                   and not (name in baseline and mapping[name] is baseline[name]))[:40]
    return [{"name": name[:120], "type": type_name(type(mapping[name]))[:100],
             "value": safe_value(mapping[name])[:240]} for name in names]


class WorkerDebugger(bdb.Bdb):
    def __init__(self, source, script_id, lines, reader, cancelled, emit, execution, namespace):
        super().__init__()
        self.baseline = dict(namespace)
        self.source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        self.source = source
        self.script_id = script_id
        self.reader = reader
        self.cancelled = cancelled
        self.emit = emit
        self.execution = execution
        self.frames = []
        self.is_stopped = False
        self._initialized = False
        self.current_frame = None
        self._pause_requested = False
        self.reset()
        self._breakpoints(lines)

    def _breakpoints(self, lines):
        lines = validate_breakpoints(lines, self.source)
        self.clear_all_breaks()
        for line in lines:
            error = self.set_break(self.script_id, line)
            if error:
                raise ValueError(error)

    def set_continue(self):
        # bdb's default removes tracing when no breakpoints exist. Keep tracing
        # so pause, cancellation and a later breakpoint remain functional.
        self._set_stopinfo(self.botframe, None, -1)

    def trace(self, frame, event, argument):
        if not self.execution._user_file(frame.f_code.co_filename):
            return None
        self.current_frame = frame
        self.execution.trace(frame, event, argument)
        if not self._initialized:
            self.botframe = frame.f_back
            self._initialized = True
            self.set_continue()
        if event != "call":
            self._commands(frame)
        self.trace_dispatch(frame, event, argument)
        return self.trace

    def checkpoint(self):
        if self.current_frame is not None:
            self._commands(self.current_frame)

    def _commands(self, frame):
        if self.cancelled.is_set():
            raise Cancelled("Debug session cancelled")
        while self.reader.poll(0):
            try:
                data = json.loads(self.reader.recv_bytes(MAX_COMMAND_BYTES))
            except EOFError:
                raise Cancelled("Debug controller closed")
            command = data.pop("command")
            # Revalidate JSON even though the pipe belongs to our trusted host.
            command_bytes(command, data)
            try:
                if command == "set_breakpoints":
                    self._breakpoints(data["lines"])
                elif command == "pause":
                    if not self.is_stopped:
                        self._pause_requested = True
                elif not self.is_stopped:
                    raise ValueError("This debug command requires a stopped session")
                elif command == "inspect":
                    self._snapshot(data["frame_index"])
                else:
                    if command == "continue":
                        self.set_continue()
                    elif command == "step_into":
                        self.set_step()
                    elif command == "step_over":
                        self.set_next(frame)
                    elif command == "step_out":
                        self.set_return(frame)
                    self.is_stopped = False
            except ValueError as error:
                self.emit("debug_error", message=str(error)[:500])
            finally:
                self.emit("debug_ack", command=command)
        if self._pause_requested and not self.is_stopped:
            self._pause_requested = False
            self._stop(frame, "pause")

    def _snapshot(self, index=0, reason="inspection", exception=None):
        if not 0 <= index < len(self.frames):
            raise ValueError("Frame is no longer available")
        frame = self.frames[index]
        fields = dict(reason=reason, source_hash=self.source_hash,
                  source_path=frame.f_code.co_filename, line=frame.f_lineno,
                  selected_frame=index,
                  stack=[{"index": i, "name": f.f_code.co_name[:120],
                          "source_path": f.f_code.co_filename[:1024], "line": f.f_lineno}
                         for i, f in enumerate(self.frames)],
                  locals=variables(frame.f_locals, self.baseline), globals=variables(frame.f_globals, self.baseline),
                  exception=exception)
        # JSON escaping may expand Unicode sixfold. Bound the final encoded
        # snapshot, not only Python string lengths, under the worker event cap.
        while len(json.dumps(fields, ensure_ascii=True).encode("utf-8")) > 48_000:
            if fields["globals"]:
                fields["globals"].pop()
            elif fields["locals"]:
                fields["locals"].pop()
            elif len(fields["stack"]) > 1:
                fields["stack"].pop()
            else:
                break
        self.emit("debug_stopped", **fields)

    def _stop(self, frame, reason, exception=None):
        self.frames = []
        current = frame
        while current is not None and len(self.frames) < 20:
            if self.execution._user_file(current.f_code.co_filename):
                self.frames.append(current)
            current = current.f_back
        self.is_stopped = True
        self.emit("status", state="paused")
        self._snapshot(reason=reason, exception=exception)
        try:
            while self.is_stopped:
                self._commands(frame)
                self.cancelled.wait(.02)
        finally:
            self.frames.clear()
        self.emit("status", state="running")

    def user_line(self, frame):
        self._stop(frame, "breakpoint" if self.break_here(frame) else "step")

    def user_return(self, frame, value):
        self._stop(frame, "return")

    def user_exception(self, frame, info):
        self._stop(frame, "exception", exception={"type": type_name(info[0])[:120],
                                                  "value": safe_value(BaseException.args.__get__(info[1], BaseException))})
