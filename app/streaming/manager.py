"""Threaded, independent, latest-frame-only Android video sessions."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
import threading
import time

from app.devices.adb import AdbClient, validate_serial
from app.devices.paths import adb_executable
from app.streaming.session import ScrcpySession, StreamError, StreamOptions, VideoFrame


@dataclass(frozen=True, slots=True)
class StreamStatus:
    state: str = "stopped"
    error: str | None = None
    frames: int = 0


@dataclass
class _Entry:
    session: ScrcpySession
    thread: threading.Thread
    status: StreamStatus
    latest: VideoFrame | None = None
    stopping: bool = False


class StreamManager:
    """All public methods are thread safe; no video/event FIFO grows unbounded.

    ``start`` starts a background upload/negotiation/decoder. ``stop`` invalidates
    its latest frame immediately, then requests background cleanup. A device
    cannot restart until its previous session thread actually exits. Errors are
    isolated per device and no automatic reconnect replays input or trust.
    """

    def __init__(self, adb: AdbClient | None = None, server_path=None, max_sessions: int = 4):
        if type(max_sessions) is not int or not 1 <= max_sessions <= 16:
            raise ValueError("max_sessions must be an integer in [1, 16]")
        self.adb = adb or AdbClient(adb_executable())
        self.server_path = Path(server_path or os.environ.get("STUDIO_SCRCPY_SERVER") or
                                Path(__file__).resolve().parents[2] / ".tools/scrcpy-server-v3.1")
        self.max_sessions = max_sessions
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.RLock()
        self._closed = False

    def start(self, serial: str, options: StreamOptions | None = None):
        validate_serial(serial)
        if options is None:
            options = StreamOptions()
        if not isinstance(options, StreamOptions):
            raise ValueError("options must be a StreamOptions instance")
        with self._lock:
            if self._closed:
                raise StreamError("Stream manager is closed")
            old = self._entries.get(serial)
            if old and old.thread.is_alive():
                raise StreamError("This device's previous video session is still running or stopping")
            if sum(entry.thread.is_alive() for entry in self._entries.values()) >= self.max_sessions:
                raise StreamError("Maximum simultaneous video sessions reached")

            def on_frame(frame):
                with self._lock:
                    entry = self._entries[serial]
                    if entry.stopping:
                        return
                    entry.latest = frame
                    entry.status = StreamStatus("streaming", None, entry.status.frames + 1)

            def on_state(state, error):
                with self._lock:
                    entry = self._entries[serial]
                    # Stop is monotonic until cleanup finishes: late decoder
                    # output cannot make the preview look live again.
                    if entry.stopping and state in ("starting", "streaming"):
                        return
                    if entry.status.state == "failed" and state == "stopped":
                        return
                    entry.status = replace(entry.status, state=state, error=error)
                    if state in ("failed", "stopped", "stopping"):
                        entry.latest = None

            session = ScrcpySession(self.adb, serial, self.server_path, options, on_frame, on_state)
            thread = threading.Thread(target=session.run, name=f"scrcpy-{serial}", daemon=True)
            self._entries[serial] = _Entry(session, thread, StreamStatus("starting"))
            thread.start()

    def stop(self, serial: str):
        with self._lock:
            entry = self._entries.get(serial)
            if entry is None:
                return
            entry.stopping = True
            entry.latest = None
            if entry.thread.is_alive() and entry.status.state != "failed":
                entry.status = replace(entry.status, state="stopping")
            entry.session.request_stop()

    def latest(self, serial: str) -> VideoFrame | None:
        with self._lock:
            entry = self._entries.get(serial)
            return entry.latest if entry else None

    def status(self, serial: str) -> StreamStatus:
        with self._lock:
            entry = self._entries.get(serial)
            return entry.status if entry else StreamStatus()

    def statuses(self) -> dict[str, StreamStatus]:
        with self._lock:
            return {serial: entry.status for serial, entry in self._entries.items()}

    def close(self, timeout: float = 0) -> bool:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 <= timeout <= 60:
            raise ValueError("timeout must be finite in [0, 60] seconds")
        with self._lock:
            self._closed = True
            for serial in self._entries:
                self.stop(serial)
            threads = [entry.thread for entry in self._entries.values()]
        deadline = time.monotonic() + timeout
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        return all(not thread.is_alive() for thread in threads)
