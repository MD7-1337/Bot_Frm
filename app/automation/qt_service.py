"""Nonblocking Qt frontend for the single-owner automation coordinator.

Importing this optional module requires PySide6; the core runtime does not.
All RuntimeCoordinator calls, including spawn and bounded cancellation, run on
one dedicated Python thread. Call ``close`` during application shutdown.
"""

from __future__ import annotations

import math
from pathlib import Path
import queue
import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from .runtime import MAX_SOURCE_BYTES, Backend, RunControl, RuntimeCoordinator


@dataclass
class _DeviceConnection:
    generation: int = 0
    allowed: bool = True
    controls: dict[str, tuple[int, RunControl]] = field(default_factory=dict)


class RuntimeService(QObject):
    """Deliver worker events to Qt without blocking the GUI thread.

    ``start`` and ``cancel`` return request IDs, not run IDs. A successful start
    emits ``event({"event": "request", "request_id": ..., "command": "start",
    "run_id": ...})``. Errors emit both ``request_error`` events and ``failure``.
    ``snapshot_changed`` carries a list of immutable ``RunInfo`` objects.

    Commands are bounded and submitted with put_nowait. Submission can raise
    ValueError, RuntimeError (closed/emergency latched), or queue.Full immediately.
    UI code should show these errors without claiming that a run started.
    Emergency stop bypasses the command queue, rejects pending commands and
    latches future starts until ``reset_emergency_stop`` succeeds.

    Device loss uses a separate per-serial generation. invalidate_device must be
    called for offline, unauthorized, disconnected, or unknown connections.
    Reconnection never resumes source. A newly approved start may explicitly
    allow_device, then start; old queued work remains stale. Starts are held at a
    worker activation gate until their generation is revalidated after spawn.
    This cannot undo a device command already in flight at invalidation time.
    """

    event = Signal(dict)
    snapshot_changed = Signal(object)
    failure = Signal(str)

    def __init__(self, max_workers: int = 4, *, queue_size: int = 64, parent: QObject | None = None):
        super().__init__(parent)
        if type(max_workers) is not int or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        if type(queue_size) is not int or queue_size < 1:
            raise ValueError("queue_size must be a positive integer")
        self._max_workers = max_workers
        self._commands: queue.Queue[tuple[str, str, dict[str, Any]]] = queue.Queue(maxsize=queue_size)
        self._shutdown = threading.Event()
        self._wake = threading.Event()
        self._emergency_pending = threading.Event()
        self._emergency_latched = threading.Event()
        # Never hold this lock while spawning, compiling, joining, emitting Qt
        # signals, or performing I/O. GUI invalidation must remain responsive.
        self._devices_lock = threading.Lock()
        self._devices: dict[str, _DeviceConnection] = {}
        self._pending_device_losses: dict[str, int] = {}
        self._assignments: dict[str, tuple[str, str]] = {}
        self._thread = threading.Thread(target=self._run, name="automation-service", daemon=True)
        self._thread.start()

    def _submit(self, command: str, **arguments: Any) -> str:
        if self._shutdown.is_set() or not self._thread.is_alive():
            raise RuntimeError("Runtime service is closed")
        request_id = uuid4().hex
        self._commands.put_nowait((command, request_id, arguments))
        self._wake.set()
        return request_id

    def start(
        self, source: str, serial: str, *, trusted: bool = False, backend: Backend = "mock",
        adb_executable: str = "adb", script_id: str = "<script>",
        project_root: str | Path | None = None, mock_config: dict | None = None, simulation_config: dict | None = None, ocr_config: dict | None = None,
        debug: bool = False, breakpoints: list[int] | None = None,
        debug_sources: dict | None = None, file_breakpoints: dict | None = None,
    ) -> str:
        """Queue a trusted script; return request ID without compiling or spawning."""
        if self._emergency_latched.is_set():
            raise RuntimeError("Emergency stop is latched; reset it before starting scripts")
        if not isinstance(source, str) or len(source) > MAX_SOURCE_BYTES:
            raise ValueError("Source must be a string of at most 1 MiB")
        # Own the queued snapshot, rather than retaining mutable host mappings
        # across the asynchronous handoff to the coordinator thread.
        if debug_sources is not None:
            if not isinstance(debug_sources, dict):
                raise ValueError('Debug sources must be a dictionary')
            debug_sources = dict(debug_sources)
        if file_breakpoints is not None:
            if not isinstance(file_breakpoints, dict):
                raise ValueError('File breakpoints must be a dictionary')
            file_breakpoints = {path: list(lines) if isinstance(lines, (list, tuple)) else lines
                                for path, lines in file_breakpoints.items()}
        self._validate_serial(serial)
        with self._devices_lock:
            device = self._devices.setdefault(serial, _DeviceConnection())
            if not device.allowed:
                raise RuntimeError(f"Device {serial!r} is unavailable; a fresh explicit start must allow it first")
            generation = device.generation
        return self._submit("start", source=source, serial=serial, trusted=trusted,
                            backend=backend, adb_executable=adb_executable, script_id=script_id,
                            project_root=project_root, mock_config=mock_config, simulation_config=simulation_config, ocr_config=ocr_config,
                            debug=debug, breakpoints=breakpoints, debug_sources=debug_sources,
                            file_breakpoints=file_breakpoints,
                            _connection_generation=generation)

    @staticmethod
    def _validate_serial(serial: str) -> None:
        if not isinstance(serial, str) or not serial or len(serial) > 256 or any(c.isspace() for c in serial) or serial.startswith("-"):
            raise ValueError("A nonempty explicit device serial is required")

    def invalidate_device(self, serial: str) -> int:
        """Latch one lost connection and cancel its controls without queue waits.

        Return the new connection generation. Queued starts from older
        generations remain stale after allow_device. Active workers immediately
        receive cooperative cancellation; the service thread performs bounded
        termination. An Android command already dispatched cannot be reversed.
        Other serials are unaffected. No scripts are automatically restarted.
        """
        self._validate_serial(serial)
        with self._devices_lock:
            device = self._devices.setdefault(serial, _DeviceConnection())
            device.generation += 1
            device.allowed = False
            self._pending_device_losses[serial] = device.generation
            for _, control in device.controls.values():
                control.cancelled.set()
            generation = device.generation
        self._wake.set()
        return generation

    def allow_device(self, serial: str) -> int:
        """Permit a fresh explicit start on the current connection generation.

        This does not resume runs or revive queued requests from an old
        connection. Cleanup of lost-generation leases is processed before fresh
        starts, so callers can allow then start after confirming availability.
        Only the GUI/device registry can establish that the phone is connected.
        """
        self._validate_serial(serial)
        if self._shutdown.is_set():
            raise RuntimeError("Runtime service is closed")
        with self._devices_lock:
            device = self._devices.setdefault(serial, _DeviceConnection())
            device.allowed = True
            return device.generation

    def cancel(self, run_id: str, grace: float = 0.5) -> str:
        """Queue cancellation; grace and process termination run off the GUI thread."""
        return self._submit("cancel", run_id=run_id, grace=grace)

    def pause(self, run_id: str) -> str:
        """Queue a pause request; actual paused state arrives from the worker."""
        return self._submit("pause", run_id=run_id)

    def resume(self, run_id: str) -> str:
        """Queue resume without blocking Qt or recreating the assigned context."""
        return self._submit("resume", run_id=run_id)

    def debug_command(self, run_id: str, command: str, **payload: Any) -> str:
        """Queue a bounded debugger command on the coordinator owner thread."""
        from .debugger import command_bytes
        command_bytes(command, payload)
        return self._submit("debug_command", run_id=run_id, debug_action=command, payload=payload)

    def emergency_stop(self) -> None:
        """Prioritize cancellation and reject queued/future starts until reset."""
        if self._shutdown.is_set():
            return
        self._emergency_latched.set()
        self._emergency_pending.set()
        self._wake.set()

    def reset_emergency_stop(self) -> str:
        """Queue a reset after receiving the ``emergency_stopped`` event."""
        if self._emergency_pending.is_set():
            raise RuntimeError("Wait for emergency_stopped before resetting emergency stop")
        return self._submit("reset_emergency_stop")

    def close(self, timeout: float = 3.0) -> bool:
        """Request shutdown and wait at most timeout seconds; use only on shutdown.

        Return False if cleanup is still running. No thread is forcibly killed;
        the application should defer final exit and retry close in that case.
        """
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("timeout must be finite nonnegative seconds")
        self._shutdown.set()
        self._wake.set()
        if threading.current_thread() is self._thread:
            return False
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _error(self, command: str, request_id: str, error: BaseException, run_id: str | None = None) -> None:
        message = f"{type(error).__name__}: {error}"[:2048]
        self.event.emit({"event": "request_error", "command": command,
                         "request_id": request_id, "message": message,
                         **({"run_id": run_id} if run_id is not None else {})})
        self.failure.emit(message)

    def _reject_pending(self, message: str) -> None:
        while True:
            try:
                command, request_id, _ = self._commands.get_nowait()
            except queue.Empty:
                return
            self._error(command, request_id, RuntimeError(message))

    def _has_device_losses(self) -> bool:
        with self._devices_lock:
            return bool(self._pending_device_losses)

    def _generation_valid(self, serial: str, generation: int) -> bool:
        # Caller holds _devices_lock.
        device = self._devices[serial]
        return device.allowed and device.generation == generation

    def _start_on_generation(self, runtime: RuntimeCoordinator, request_id: str, arguments: dict[str, Any]) -> str:
        generation = arguments.pop("_connection_generation")
        serial = arguments["serial"]
        control = runtime.create_control()
        with self._devices_lock:
            if not self._generation_valid(serial, generation):
                raise RuntimeError("Start rejected: device connection generation changed or is unavailable")
            self._devices[serial].controls[request_id] = (generation, control)
        try:
            # The child stays at its activation gate throughout process.start.
            # Invalidation can set its pre-registered cancellation event meanwhile.
            run_id = runtime.start(**arguments, control=control)
            self._assignments[run_id] = (serial, request_id)
            with self._devices_lock:
                valid = self._generation_valid(serial, generation) and not control.cancelled.is_set()
                if valid and not self._shutdown.is_set() and not self._emergency_latched.is_set():
                    control.activation.set()
                else:
                    valid = False
                    control.cancelled.set()
            if not valid:
                runtime.cancel(run_id, grace=0.05)
                raise RuntimeError("Start cancelled before activation: device connection or stop state changed")
            return run_id
        except BaseException:
            # An assigned child remains tracked until its terminal snapshot;
            # unsuccessful spawns have no process and can release the gate now.
            if not any(request_id == item[1] for item in self._assignments.values()):
                with self._devices_lock:
                    self._devices[serial].controls.pop(request_id, None)
            raise

    def _process_device_losses(self, runtime: RuntimeCoordinator) -> None:
        with self._devices_lock:
            losses = self._pending_device_losses
            self._pending_device_losses = {}
        runs = runtime.snapshot()
        for serial, generation in losses.items():
            cancelled = []
            for run in runs:
                if run.serial != serial or run.exitcode is not None:
                    continue
                assignment = self._assignments.get(run.run_id)
                if assignment is None:
                    continue
                with self._devices_lock:
                    registered = self._devices[serial].controls.get(assignment[1])
                if registered is not None and registered[0] < generation:
                    runtime.cancel(run.run_id, grace=0.05)
                    cancelled.append(run.run_id)
            self.event.emit({"event": "device_invalidated", "serial": serial,
                             "generation": generation, "cancelled_run_ids": cancelled})

    def _release_terminal_controls(self, snapshot: list[Any]) -> None:
        for run in snapshot:
            if run.exitcode is None:
                continue
            assignment = self._assignments.pop(run.run_id, None)
            if assignment is not None:
                serial, request_id = assignment
                with self._devices_lock:
                    self._devices[serial].controls.pop(request_id, None)

    def _run(self) -> None:
        runtime = None
        last_snapshot = None
        try:
            runtime = RuntimeCoordinator(max_workers=self._max_workers)
            while not self._shutdown.is_set():
                self._wake.clear()
                self._process_device_losses(runtime)
                if self._emergency_pending.is_set():
                    self._reject_pending("Request cancelled by emergency stop")
                    for run in runtime.snapshot():
                        if run.exitcode is None:
                            runtime.cancel(run.run_id, grace=0.05)
                    for event in runtime.poll():
                        self.event.emit(event)
                    self._emergency_pending.clear()
                    self.event.emit({"event": "emergency_stopped"})

                # Bound work per service tick so noisy submissions cannot starve
                # worker polling or priority emergency/close requests.
                for _ in range(4):
                    if self._shutdown.is_set() or self._emergency_pending.is_set() or self._has_device_losses():
                        break
                    try:
                        command, request_id, arguments = self._commands.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        if command == "start":
                            if self._emergency_latched.is_set():
                                raise RuntimeError("Emergency stop is latched")
                            run_id = self._start_on_generation(runtime, request_id, arguments)
                            response = {"run_id": run_id}
                        elif command == "cancel":
                            runtime.cancel(**arguments)
                            response = {"run_id": arguments["run_id"]}
                        elif command in {"pause", "resume"}:
                            getattr(runtime, command)(**arguments)
                            response = {"run_id": arguments["run_id"]}
                        elif command == "debug_command":
                            runtime.debug_command(arguments["run_id"], arguments["debug_action"], **arguments["payload"])
                            response = {"run_id": arguments["run_id"]}
                        elif command == "reset_emergency_stop":
                            self._emergency_latched.clear()
                            response = {}
                        else:
                            raise ValueError("Unknown runtime service command")
                        self.event.emit({"event": "request", "command": command,
                                         "request_id": request_id, **response})
                    except Exception as error:
                        self._error(command, request_id, error, arguments.get("run_id"))

                for event in runtime.poll():
                    self.event.emit(event)
                current = runtime.snapshot()
                self._release_terminal_controls(current)
                if current != last_snapshot:
                    self.snapshot_changed.emit(current)
                    last_snapshot = current
                self._wake.wait(0.02)
        except BaseException as error:
            self.failure.emit(f"Runtime service failed: {type(error).__name__}: {error}"[:2048])
        finally:
            self._shutdown.set()
            self._reject_pending("Runtime service is shutting down")
            if runtime is not None:
                try:
                    runtime.close()
                except BaseException as error:
                    self.failure.emit(f"Runtime cleanup failed: {type(error).__name__}: {error}"[:2048])
            with self._devices_lock:
                for device in self._devices.values():
                    device.controls.clear()
                self._assignments.clear()
            self.event.emit({"event": "service_closed"})
