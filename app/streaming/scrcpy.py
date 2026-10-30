"""Managed external scrcpy fallback, deliberately separate from Qt embedding.

Pinned integration candidate: scrcpy 3.1 (Apache-2.0), official Genymobile
release. The external window is a fallback only. Embedded transport requires
a matching server/client protocol and real-device validation before release.
No media protocol is guessed or presented as proven by this adapter.
"""

from __future__ import annotations

import subprocess

from app.devices.adb import validate_serial


class ScrcpyError(RuntimeError):
    pass


class ExternalScrcpy:
    def __init__(self, executable: str = "scrcpy") -> None:
        self.executable = executable
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    def version(self) -> str:
        try:
            result = subprocess.run([self.executable, "--version"], capture_output=True, timeout=10, check=False, shell=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ScrcpyError(f"scrcpy dependency check failed: {error}") from error
        if result.returncode:
            raise ScrcpyError("scrcpy --version failed.")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def start(self, serial: str) -> None:
        validate_serial(serial)
        existing = self._processes.get(serial)
        if existing and existing.poll() is None:
            raise ScrcpyError("An external preview for this device is already running.")
        try:
            self._processes[serial] = subprocess.Popen(
                [self.executable, "--serial", serial, "--no-audio", "--window-title", f"Android Automation Studio — {serial}"],
                stdin=subprocess.DEVNULL,
                # Do not leave unconsumed PIPEs that may deadlock a long run.
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        except OSError as error:
            raise ScrcpyError(f"Could not start scrcpy: {error}") from error

    def is_running(self, serial: str) -> bool:
        process = self._processes.get(serial)
        return process is not None and process.poll() is None

    def stop(self, serial: str) -> None:
        process = self._processes.pop(serial, None)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def close(self) -> None:
        for serial in list(self._processes):
            self.stop(serial)
