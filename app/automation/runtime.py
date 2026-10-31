"""Bounded, serial-specific execution of trusted Python automation scripts.

Application messages use JSON over ``send_bytes``/``recv_bytes``; no application
message is deserialized with pickle. The OS pipe provides backpressure. Spawn's
own trusted bootstrap is Python multiprocessing machinery, not an exposed API.

This executes ordinary, explicitly trusted Python with host-user permissions.
It does not prevent a script from importing subprocess or accessing other phones
outside the supplied API. Device leases cover this coordinator instance only.
"""

from __future__ import annotations

import contextlib
import io
import json
import linecache
import math
import multiprocessing as mp
from multiprocessing.connection import Connection
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from dataclasses import dataclass, replace
from typing import Any, Literal
from types import ModuleType
from uuid import uuid4

from app.automation.api.errors import Cancelled as ScriptCancelled
from app.automation.recovery import classify_failure

MAX_MESSAGE_BYTES = 64 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
Backend = Literal["mock", "adb", "simulation"]


class TrustRequiredError(PermissionError):
    """The caller has not explicitly approved trusted Python execution."""


class DeviceBusyError(RuntimeError):
    """An active run already owns this serial in the coordinator."""


class WorkerLimitError(RuntimeError):
    """The configured concurrent worker limit has been reached."""


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    serial: str
    script_id: str
    backend: Backend
    state: str = "starting"
    pid: int | None = None
    exitcode: int | None = None


@dataclass
class _Run:
    info: RunInfo
    process: Any
    reader: Connection | None
    cancelled: Any
    activation: Any
    paused: Any
    debug_writer: Any = None
    debug_pending: bool = False


@dataclass(frozen=True)
class RunControl:
    """Spawn-compatible gates registered before a service activates a worker.

    Setting cancellation is thread safe and does not join or terminate a process.
    Activation must only be granted after connection-generation revalidation.
    """

    cancelled: Any
    activation: Any
    paused: Any = None


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def _coordinate(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 0 <= value <= 65535:
        raise ValueError(f"{name} must be between 0 and 65535")
    return value


class _ExecutionControl:
    """Per-worker pause/cancellation and throttled source location reporting."""

    def __init__(self, cancelled: Any, paused: Any, emit: Any, script_id: str,
                 script_directory: str, project_root: str):
        self.cancelled = cancelled
        self.paused = paused
        self.emit = emit
        self.script_id = script_id
        self.script_directory = Path(script_directory)
        self.project_root = Path(project_root)
        self._excluded_roots = (Path(__file__).resolve().parents[1],
                                Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())
        self.debug_checkpoint = None
        self._paused_acknowledged = False
        self._cancel_delivered = False
        self._traced_files: dict[str, bool] = {}
        self._last_line_at = 0.0
        self._last_line: tuple[str, int] | None = None
        self._observed_line: tuple[str, int] | None = None
        self._line_lock = threading.Lock()
        self._reporting_stop = threading.Event()
        self._reporter: threading.Thread | None = None

    def _report_line(self) -> None:
        # One latest-value mailbox, not an event for every Python trace call.
        # The timer also flushes a source line that entered a blocking API call
        # during the throttle interval, even when no further line is executed.
        with self._line_lock:
            location = self._observed_line
            now = time.monotonic()
            if location is None or location == self._last_line or (
                    self._last_line is not None and now - self._last_line_at < .05):
                return
            self._last_line_at = now
            self._last_line = location
            # Serialize selection and emission across trace/reporter threads so
            # a delayed older update cannot arrive after a newer source line.
            self.emit("line", source_path=location[0], line=location[1])

    def start_reporting(self) -> None:
        def report():
            while not self._reporting_stop.wait(.05):
                try:
                    self._report_line()
                except (OSError, ValueError):
                    return
        self._reporter = threading.Thread(target=report, name="script-source-location", daemon=True)
        self._reporter.start()

    def stop_reporting(self) -> None:
        self._reporting_stop.set()
        if self._reporter is not None:
            self._reporter.join(timeout=.2)

    def checkpoint(self) -> None:
        if self.cancelled.is_set():
            self._cancel_delivered = True
            raise ScriptCancelled("Cancellation requested")
        if self.debug_checkpoint is not None:
            self.debug_checkpoint()
        while self.paused.is_set():
            if not self._paused_acknowledged:
                self.emit("status", state="paused")
                self._paused_acknowledged = True
            if self.cancelled.wait(0.02):
                self._cancel_delivered = True
                raise ScriptCancelled("Cancelled while paused")
        if self._paused_acknowledged:
            self._paused_acknowledged = False
            self.emit("status", state="running")

    def interruptible_wait(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            self.checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.cancelled.wait(min(remaining, 0.02))

    def _user_file(self, filename: str) -> bool:
        if filename == self.script_id:
            return True
        cached = self._traced_files.get(filename)
        if cached is not None:
            return cached
        result = False
        # Embedded PySide helpers can use virtual relative filenames such as
        # shibokensupport/signature/loader.py. Resolving those against the
        # worker cwd falsely marks dependency lines as project source.
        if not filename.startswith("<") and Path(filename).is_absolute():
            path = Path(filename).resolve()
            result = (not any(path.is_relative_to(excluded) for excluded in self._excluded_roots)
                      and (path.is_relative_to(self.script_directory)
                           or path.is_relative_to(self.project_root / "scripts")))
        self._traced_files[filename] = result
        return result

    def trace(self, frame, event, argument):
        if not self._user_file(frame.f_code.co_filename):
            return None
        if event == "line":
            location = (frame.f_code.co_filename, frame.f_lineno)
            with self._line_lock:
                self._observed_line = location
            self._report_line()
            # A cancellation is catchable so user cleanup may execute. API calls
            # still reject all further actions; a non-cooperating cleanup loop
            # remains subject to the coordinator's bounded forced termination.
            # Pause ordinary project Python at a line boundary. Running code
            # outside API safe points remains subject to bounded forced stop;
            # a trace hook is not a general-purpose Python interruption engine.
            if ((self.paused.is_set() or self._paused_acknowledged)
                    and not (self.cancelled.is_set() and self._cancel_delivered)):
                self.checkpoint()
        return self.trace


class _EventWriter(io.TextIOBase):
    def __init__(self, emit: Any, stream: str):
        self.emit = emit
        self.stream = stream

    def write(self, text: str) -> int:
        # Bound each event; avoid buffering arbitrarily long print statements.
        for offset in range(0, len(text), 2048):
            self.emit("output", stream=self.stream, text=text[offset:offset + 2048])
        return len(text)

    def flush(self) -> None:
        return None


@contextlib.contextmanager
def _main_namespace(script_id: str, bindings: dict[str, Any]):
    """Execute source as a real main module inside this worker process only.

    A plain globals dictionary with a made-up __name__ breaks main guards and
    decorators that resolve forward annotations through sys.modules. Restore
    multiprocessing's bootstrap module afterwards rather than modifying the
    parent interpreter or leaving a synthetic main module behind.
    """
    module = ModuleType("__main__")
    module.__dict__.update(bindings)
    module.__dict__.update(__name__="__main__", __file__=script_id,
                           __package__=None, __spec__=None,
                           __cached__=None, __loader__=None)
    missing = object()
    previous = sys.modules.get("__main__", missing)
    sys.modules["__main__"] = module
    try:
        yield module.__dict__
    finally:
        if previous is missing:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = previous


def _worker(
    source: str, serial: str, backend: Backend, adb_executable: str,
    script_id: str, run_id: str, writer: Connection, cancelled: Any, activation: Any,
    paused: Any, project_root: str, script_directory: str, mock_config: dict | None, simulation_config: dict | None, ocr_config: dict | None,
    debug_reader: Connection | None = None, breakpoints: list[int] | None = None,
    debug_sources: dict | None = None, file_breakpoints: dict | None = None,
) -> None:
    emission_lock = threading.Lock()
    missing_cache = object()
    previous_cache = linecache.cache.get(script_id, missing_cache)
    # Report the exact executed source, including an unsaved editor buffer,
    # rather than accidentally reading an older file from disk on failure.
    linecache.cache[script_id] = (len(source), None, source.splitlines(keepends=True), script_id)

    def emit(event: str, **fields: Any) -> None:
        payload = {"event": event, "run_id": run_id, "serial": serial,
                   "script_id": script_id, "backend": backend, "timestamp": time.time(), **fields}
        data = json.dumps(payload, allow_nan=False, ensure_ascii=True).encode("utf-8")
        if len(data) > MAX_MESSAGE_BYTES:
            raise ValueError("Worker event exceeds message limit")
        with emission_lock:
            writer.send_bytes(data)

    try:
        # A service may spawn while a GUI connection invalidation arrives. Never
        # initialize a device context or run source until that service revalidates
        # the connection generation and grants activation.
        while not activation.wait(0.02):
            if cancelled.is_set():
                raise ScriptCancelled("Cancelled before worker activation")
        if cancelled.is_set():
            raise ScriptCancelled("Cancelled before worker activation")
        from app.automation.api import Device, use_device
        from app.automation.backends import AdbBackend, MockBackend
        from app.vision.ocr import TesseractOCR
        from app.projects.library import AssetLibrary

        # Paths/cwd belong to this process only. Ordinary Python imports remain
        # available; this is trusted execution, not a restricted namespace.
        for directory in (project_root, str(Path(project_root) / "scripts"), script_directory):
            if directory not in sys.path:
                sys.path.insert(0, directory)
        os.chdir(script_directory)
        execution = _ExecutionControl(cancelled, paused, emit, script_id, script_directory, project_root)
        if backend == "simulation":
            from app.simulation.model import SimulationClient
            adapter = SimulationClient(serial, simulation_config)
        else:
            adapter = AdbBackend(serial, adb_executable) if backend == "adb" else MockBackend(serial, mock_config)
        context = Device(adapter, AssetLibrary(project_root, script_dir=script_directory),
                         checkpoint=execution.checkpoint,
                         interruptible_wait=execution.interruptible_wait, emit=emit,
                         ocr=TesseractOCR(**(ocr_config or {})))
        emit("status", state="running")
        with contextlib.redirect_stdout(_EventWriter(emit, "stdout")), contextlib.redirect_stderr(_EventWriter(emit, "stderr")), use_device(context), _main_namespace(script_id, context.bindings()) as namespace:
            execution.checkpoint()
            execution.start_reporting()
            debugger = None
            if debug_reader is not None:
                from app.automation.debugger import WorkerDebugger
                debugger = WorkerDebugger(source, script_id, breakpoints or [], debug_reader,
                                          cancelled, emit, execution, namespace, debug_sources, file_breakpoints)
                execution.debug_checkpoint = debugger.checkpoint
                emit("debug_started", source_hash=debugger.source_hash, breakpoints=breakpoints or [],
                     source_file_count=len(debugger.sources))
            sys.settrace(debugger.trace if debugger is not None else execution.trace)
            try:
                from app.automation.debug_sources import imported_sources
                with imported_sources(debug_sources or {}, keep_cache=True) if debugger is not None else contextlib.nullcontext():
                    exec(compile(source, script_id, "exec"), namespace, namespace)
                execution.checkpoint()
            finally:
                sys.settrace(None)
                execution.stop_reporting()
        emit("status", state="completed")
    except ScriptCancelled:
        emit("status", state="cancelled")
    except BaseException as error:
        sys.settrace(None)
        frames = traceback.extract_tb(error.__traceback__)
        user_frames = [frame for frame in frames if frame.filename == script_id or
                       (not frame.filename.startswith("<") and Path(frame.filename).is_absolute() and
                        Path(frame.filename).resolve().is_relative_to(Path(project_root)) and
                        not Path(frame.filename).resolve().is_relative_to(Path(__file__).resolve().parents[1]))]
        location = user_frames[-1] if user_frames else None
        try:
            message = str(error)
        except BaseException:
            message = "Exception message could not be formatted"
        emit("error", error_type=type(error).__name__[:200], message=message[:2000],
             failure=classify_failure(error),
             source_path=(location.filename if location else script_id)[:1024],
             source_line=location.lineno if location else None,
             traceback="".join(traceback.format_exception(type(error), error, error.__traceback__))[-6000:])
        emit("status", state="failed")
        raise SystemExit(1)
    finally:
        if previous_cache is missing_cache:
            linecache.cache.pop(script_id, None)
        else:
            linecache.cache[script_id] = previous_cache
        writer.close()
        if debug_reader is not None:
            debug_reader.close()


class RuntimeCoordinator:
    """Manage bounded spawned runs and exclusive in-process serial leases.

    Call start/poll/cancel/snapshot/close from one owner thread (normally Qt's UI
    thread). API cancellation is cooperative; arbitrary Python requires terminate
    after the grace period. A sent Android command cannot be undone. Ordinary
    Python can bypass these API limits; ``trusted=True`` is approval, not a sandbox.
    """

    def __init__(self, max_workers: int = 4):
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        self.max_workers = max_workers
        self._context = mp.get_context("spawn")
        self._runs: dict[str, _Run] = {}
        self._closed = False
        self._owner = threading.get_ident()

    def _check_owner(self) -> None:
        if threading.get_ident() != self._owner:
            raise RuntimeError("Coordinator methods must run on the owner thread")

    def create_control(self) -> RunControl:
        """Create an inactive worker gate on this coordinator's owner thread."""
        self._check_owner()
        if self._closed:
            raise RuntimeError("Coordinator is closed")
        return RunControl(self._context.Event(), self._context.Event(), self._context.Event())

    def start(
        self, source: str, serial: str, *, trusted: bool = False,
        backend: Backend = "mock", adb_executable: str = "adb", script_id: str = "<script>",
        control: RunControl | None = None,
        project_root: str | Path | None = None, mock_config: dict | None = None, simulation_config: dict | None = None, ocr_config: dict | None = None,
        debug: bool = False, breakpoints: list[int] | None = None,
        debug_sources: dict | None = None, file_breakpoints: dict | None = None,
    ) -> str:
        """Run trusted Python on one serial and return a unique run ID.

        Raises TrustRequiredError, DeviceBusyError, WorkerLimitError, ValueError,
        or SyntaxError before a process starts. Call from a guarded ``__main__``
        entry point on Windows, as required by multiprocessing spawn.
        """
        self._check_owner()
        if self._closed:
            raise RuntimeError("Coordinator is closed")
        if trusted is not True:
            raise TrustRequiredError("Explicit approval is required: scripts have host-user permissions")
        if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise ValueError("Source must be a string of at most 1 MiB")
        if not isinstance(serial, str) or not serial or len(serial) > 256 or any(c.isspace() for c in serial) or serial.startswith("-"):
            raise ValueError("A nonempty explicit device serial is required")
        if backend not in ("mock", "adb", "simulation"):
            raise ValueError("backend must be 'mock', 'adb' or 'simulation'")
        from app.simulation.model import is_simulation, SimulationClient
        if backend == "simulation":
            SimulationClient(serial, simulation_config)
            simulation_config = dict(simulation_config)
        elif is_simulation(serial) or simulation_config is not None:
            raise ValueError("Simulation identities/capabilities require the simulation backend")
        if not isinstance(script_id, str) or len(script_id) > 1024:
            raise ValueError("script_id must be a string of at most 1024 characters")
        from app.projects.library import AssetLibrary, discover_project
        script_path = None if script_id.startswith("<") and script_id.endswith(">") else Path(script_id).resolve()
        root = Path(project_root).resolve() if project_root is not None else (discover_project(script_path) if script_path is not None else Path.cwd().resolve())
        script_directory = script_path.parent if script_path is not None else root
        # Validate containment/existence before spawning; no parent cwd changes.
        AssetLibrary(root, script_dir=script_directory)
        if mock_config is not None:
            if backend != "mock" or not isinstance(mock_config, dict):
                raise ValueError("mock_config is available only for explicit mock runs")
            try:
                encoded_config = json.dumps(mock_config, allow_nan=False)
            except (TypeError, ValueError) as error:
                raise ValueError("mock_config must contain finite JSON primitives") from error
            if len(encoded_config.encode("utf-8")) > 128 * 1024:
                raise ValueError("mock_config exceeds the supported size")
            mock_config = json.loads(encoded_config)
        if ocr_config is not None:
            if not isinstance(ocr_config, dict) or set(ocr_config) != {"executable"} or not isinstance(ocr_config["executable"], str) or len(ocr_config["executable"])>4096 or "\x00" in ocr_config["executable"]:
                raise ValueError("OCR configuration accepts only an explicit executable path")
            ocr_config = dict(ocr_config)
        if type(debug) is not bool:
            raise ValueError("debug must be a boolean")
        from app.automation.debugger import validate_breakpoints
        breakpoints = validate_breakpoints([] if breakpoints is None else breakpoints, source)
        if breakpoints and not debug:
            raise ValueError("Breakpoints require debug mode")
        from app.automation.debug_sources import validate_sources
        if not debug and (debug_sources is not None or file_breakpoints):
            raise ValueError('Source snapshots and file breakpoints require debug mode')
        debug_sources = validate_sources(debug_sources or {script_id: source}, root, script_id, source) if debug else None
        if file_breakpoints is not None and (not isinstance(file_breakpoints, dict)
                or len(file_breakpoints) > 200):
            raise ValueError('Invalid file breakpoint map')
        checked_breakpoints = {}
        for path, values in (file_breakpoints or {}).items():
            if path not in (debug_sources or {}):
                raise ValueError('Breakpoint file is not in the approved source snapshots')
            checked_breakpoints[path] = validate_breakpoints(values, debug_sources[path])
        if sum(len(values) for values in checked_breakpoints.values()) + len(breakpoints) > 200:
            raise ValueError('At most 200 breakpoints may be active in one run')
        compile(source, script_id, "exec")
        active = [run for run in self._runs.values() if run.process is not None and run.process.is_alive()]
        if any(run.info.serial == serial for run in active):
            raise DeviceBusyError(f"Device {serial!r} is already leased")
        if len(active) >= self.max_workers:
            raise WorkerLimitError("Concurrent worker limit reached")
        run_id = uuid4().hex
        reader, writer = self._context.Pipe(duplex=False)
        if control is None:
            control = self.create_control()
            control.activation.set()
        elif not isinstance(control, RunControl):
            raise TypeError("control must be a RunControl created by create_control")
        if control.paused is None:
            # Compatibility for a caller holding an older two-event RunControl.
            control = RunControl(control.cancelled, control.activation, self._context.Event())
        cancelled = control.cancelled
        debug_reader, debug_writer = self._context.Pipe(duplex=False) if debug else (None, None)
        process = self._context.Process(
            target=_worker,
            args=(source, serial, backend, adb_executable, script_id, run_id, writer, cancelled, control.activation,
                  control.paused, str(root), str(script_directory), mock_config, simulation_config, ocr_config,
                  debug_reader, breakpoints, debug_sources, checked_breakpoints),
            name=f"automation-{run_id[:8]}",
        )
        try:
            process.start()
        except BaseException:
            reader.close()
            writer.close()
            if debug_reader is not None:
                debug_reader.close()
                debug_writer.close()
            raise
        if debug_reader is not None:
            debug_reader.close()
        writer.close()
        # Retain both synchronization objects until the spawn bootstrap has
        # rebuilt them; dropping activation early can unlink its POSIX semaphore.
        self._runs[run_id] = _Run(RunInfo(run_id, serial, script_id, backend, pid=process.pid), process, reader, cancelled, control.activation, control.paused, debug_writer)
        return run_id

    def poll(self, limit: int = 256) -> list[dict[str, Any]]:
        """Drain at most ``limit`` JSON events without blocking the owner thread.

        The pipe bounds pending events and exerts backpressure. Consumers must
        poll regularly; an unpolled noisy script may block until cancellation.
        """
        self._check_owner()
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        events: list[dict[str, Any]] = []
        while len(events) < limit:
            received = False
            for run in self._runs.values():
                reader = run.reader
                if reader is None:
                    continue
                try:
                    if not reader.poll(0):
                        continue
                    data = reader.recv_bytes(MAX_MESSAGE_BYTES)
                    event = json.loads(data)
                    if not isinstance(event, dict) or event.get("run_id") != run.info.run_id or event.get("serial") != run.info.serial:
                        raise ValueError("Invalid worker event identity")
                    if event.get("event") == "debug_ack":
                        run.debug_pending = False
                    if event.get("event") == "status":
                        state = event.get("state")
                        if state not in TERMINAL_STATES | {"running", "paused"}:
                            raise ValueError("Invalid worker state")
                        # A forced stop can finish before older pipe statuses
                        # are consumed. Never let a queued running/paused event
                        # revive a terminal process in the snapshot.
                        if run.info.exitcode is None or run.info.state not in TERMINAL_STATES:
                            run.info = replace(run.info, state=state)
                    events.append(event)
                    received = True
                except EOFError:
                    reader.close()
                    run.reader = None
                except (OSError, ValueError, UnicodeError) as error:
                    reader.close()
                    run.reader = None
                    run.cancelled.set()
                    run.info = replace(run.info, state="failed")
                    events.append({"event": "error", "run_id": run.info.run_id,
                                   "serial": run.info.serial, "backend": run.info.backend,
                                   "error_type": "IPCError", "message": str(error)})
                    received = True
                if len(events) >= limit:
                    break
            if not received:
                break
        self._refresh()
        return events

    def _refresh(self) -> None:
        for run in self._runs.values():
            if run.process is None:
                continue
            if not run.process.is_alive():
                run.process.join(timeout=0)
                state = run.info.state
                if state not in TERMINAL_STATES and run.reader is None:
                    state = "cancelled" if run.cancelled.is_set() else "failed"
                run.info = replace(run.info, state=state, exitcode=run.process.exitcode)
                if run.reader is None:
                    run.process.close()
                    run.process = None
                    if run.debug_writer is not None:
                        run.debug_writer.close()
                        run.debug_writer = None
                    run.cancelled = None
                    run.activation = None
                    run.paused = None

    def snapshot(self) -> list[RunInfo]:
        """Return immutable run states; call poll first to consume status events."""
        self._check_owner()
        self._refresh()
        return [run.info for run in self._runs.values()]

    def cancel(self, run_id: str, grace: float = 0.5) -> None:
        """Request cancellation, then terminate after bounded grace.

        This may block the caller for up to grace plus bounded termination waits;
        a UI should use a short grace or dispatch through its owner service.
        Already-sent Android input cannot be reversed.
        """
        self._check_owner()
        grace = _number(grace, "grace")
        if grace > 30:
            raise ValueError("grace must not exceed 30 seconds")
        run = self._runs[run_id]
        if run.process is None:
            return
        if not run.process.is_alive():
            return
        run.cancelled.set()
        deadline = time.monotonic() + grace
        # Drain no application messages here: poll remains the sole event consumer.
        run.process.join(timeout=max(0, deadline - time.monotonic()))
        if run.process.is_alive():
            run.process.terminate()
            run.process.join(timeout=1)
        if run.process.is_alive():
            run.process.kill()
            run.process.join(timeout=1)
        if run.process.is_alive():
            raise RuntimeError(f"Worker {run_id} could not be stopped")
        run.info = replace(run.info, state="cancelled", exitcode=run.process.exitcode)

    def debug_command(self, run_id: str, command: str, **payload: Any) -> None:
        """Send one bounded private command without blocking a GUI/service tick.

        At most one command may await acknowledgment. The maximum 3072-byte
        message fits an empty local pipe; no arbitrary command backlog builds up.
        Poll debug_ack before submitting the next command.
        """
        self._check_owner()
        from app.automation.debugger import command_bytes
        data = command_bytes(command, payload)
        run = self._runs[run_id]
        if run.debug_writer is None or run.process is None or not run.process.is_alive():
            raise RuntimeError("Run has no active debugger")
        if run.debug_pending:
            raise RuntimeError("Wait for the preceding debug command acknowledgment")
        run.debug_writer.send_bytes(data)
        run.debug_pending = True

    def pause(self, run_id: str) -> None:
        """Request cooperative pause; worker status acknowledges the safe point."""
        self._check_owner()
        if self._closed:
            raise RuntimeError("Coordinator is closed")
        run = self._runs[run_id]
        if run.process is None or not run.process.is_alive():
            raise RuntimeError("Only an active run can be paused")
        if run.debug_writer is not None:
            self.debug_command(run_id, "pause")
        else:
            run.paused.set()

    def resume(self, run_id: str) -> None:
        """Resume an active worker; no source or device context is recreated."""
        self._check_owner()
        if self._closed:
            raise RuntimeError("Coordinator is closed")
        run = self._runs[run_id]
        if run.process is None or not run.process.is_alive():
            raise RuntimeError("Only an active run can be resumed")
        if run.debug_writer is not None:
            self.debug_command(run_id, "continue")
        else:
            run.paused.clear()

    def close(self) -> None:
        """Stop owned workers and close all pipe handles. Idempotent."""
        self._check_owner()
        if self._closed:
            return
        for run_id, run in self._runs.items():
            self.cancel(run_id, grace=0.1)
            if run.reader is not None:
                run.reader.close()
                run.reader = None
            if run.process is not None:
                run.process.close()
                run.process = None
            if run.debug_writer is not None:
                run.debug_writer.close()
                run.debug_writer = None
            run.cancelled = None
            run.activation = None
            run.paused = None
        self._closed = True

    def __enter__(self) -> RuntimeCoordinator:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
