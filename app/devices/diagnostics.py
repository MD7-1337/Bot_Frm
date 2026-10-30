"""Cancellable staged connection checks; no Qt calls, privilege changes or server kills."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import platform
import re
import shutil
import threading
import time

from app.devices.adb import AdbClient, png_dimensions


SOLUTIONS = {
    "binary": "Choose an executable ADB in Settings. Source checkouts exclude downloaded tools: run python tools/fetch_adb.py without sudo. On Windows choose adb.exe from platform-tools.",
    "version": "Check ADB path/executable permissions and required host libraries. A stale system ADB may conflict with another SDK installation; select the intended platform-tools binary explicitly.",
    "server": "Another program may own port 5037, or host policy may block ADB/local sockets. Use matching SDK/ADB versions: ADB itself can restart an incompatible server. Diagnostics does not issue kill-server. Ask school IT if policy blocks access.",
    "discovery": "Use a data-capable USB cable, unlock the phone and enable USB debugging. Linux USB permissions require host udev/group access; without sudo ask IT, or use permitted Android 11+ Wireless debugging. Windows may need the OEM USB driver.",
    "authorization": "Authorize USB debugging on the unlocked phone. Offline: check cable/Wi-Fi and refresh. USB permissions denied: ask the computer administrator for udev/group access; app code cannot bypass it. Select an authorized phone, then diagnose again.",
    "query": "Refresh after unlocking/reconnecting. Check that the exact serial is authorized and the selected ADB server can address it.",
    "screenshot": "The phone may have disconnected, or Android/app security policy may restrict screen capture. Check the phone and try its home screen. Protected content may remain black.",
    "video": "Use the pinned scrcpy 3.1 server (python tools/fetch_scrcpy.py). Check PyAV/H.264 dependencies and codec support. Try a lower stream size/FPS; screenshot fallback remains available and is not video.",
}
STAGES = (("binary", "ADB executable"), ("version", "ADB version"), ("server", "ADB server response"),
          ("discovery", "Device discovery"), ("authorization", "Authorized device"),
          ("query", "Harmless Android query"), ("screenshot", "Screenshot capture"), ("video", "Real decoded video frame"))


@dataclass(frozen=True)
class DiagnosticStep:
    key: str
    title: str
    state: str
    detail: str
    advice: str = ""


@dataclass
class DiagnosticReport:
    executable: str
    platform: str = field(default_factory=platform.platform)
    steps: list[DiagnosticStep] = field(default_factory=list)
    serials: list[str] = field(default_factory=list)

    def text(self, redact_serials=True):
        rows = ["Android Automation Studio — connection diagnostics", f"Host: {self.platform}",
                f"ADB: {self.executable}", "Checks are observations on this host; skipped checks are NOT VERIFIED."]
        for step in self.steps:
            rows.append(f"\n[{step.state.upper()}] {step.title}\n{step.detail}")
            if step.advice:
                rows.append("Next: " + step.advice)
        value = "\n".join(rows)
        # Reports never run pairing or store its code. Also redact any generic
        # pairing-code text returned by a custom ADB binary/error wrapper.
        value = re.sub(r"(?i)((?:pairing[ _-]?)?code\s*[:=]\s*)\S+", r"\1[REDACTED]", value)
        if redact_serials:
            for index, serial in enumerate(sorted(set(self.serials), key=len, reverse=True), 1):
                value = value.replace(serial, f"[device-{index}]")
        return value.replace(str(Path.home()), "~")


class ConnectionDiagnostics:
    def __init__(self, adb, streams, *, progress=None, cancel=None, video_timeout=12):
        self.adb = adb
        self.streams = streams
        self.progress = progress or (lambda step: None)
        self.cancel = cancel if cancel is not None else threading.Event()
        self.video_timeout = video_timeout

    def run(self, selected=None, *, video=True):
        report = DiagnosticReport(self.adb.executable)
        if selected:
            report.serials.append(selected)
        values = {}
        failed = False
        owned_stream = False
        serial = None
        try:
            for key, title in STAGES:
                if failed or self.cancel.is_set() or (key == "video" and not video):
                    reason = "Cancelled" if self.cancel.is_set() else "Video check disabled" if key == "video" and not video else "Earlier check did not pass"
                    step = DiagnosticStep(key, title, "not verified", reason, SOLUTIONS[key])
                else:
                    self.progress(DiagnosticStep(key, title, "running", "Checking…"))
                    try:
                        if key == "binary":
                            resolved = shutil.which(self.adb.executable)
                            if resolved is None:
                                raise RuntimeError(f"ADB is missing or not executable: {self.adb.executable}")
                            detail = str(Path(resolved).resolve())
                        elif key == "version":
                            detail = self.adb.version()
                        elif key == "server":
                            self.adb.start_server()
                            detail = "ADB start-server responded successfully; no explicit kill-server command was issued."
                            for name in ("ADB_SERVER_SOCKET", "ANDROID_ADB_SERVER_PORT"):
                                if os.environ.get(name):
                                    detail += f" {name} is configured (custom server routing)."
                        elif key == "discovery":
                            listing = self.adb.device_listing()
                            devices = AdbClient.parse_devices(listing)
                            values["devices"] = devices
                            report.serials.extend(device.serial for device in devices)
                            detail = listing.strip() or "Empty device-list output"
                        elif key == "authorization":
                            devices = values["devices"]
                            current = next((device for device in devices if device.serial == selected), None) if selected else None
                            if selected and (current is None or not current.available):
                                raise RuntimeError(f"Selected phone {selected}: {current.state if current else 'not detected'}")
                            available = [device for device in devices if device.available]
                            if current is None and len(available) != 1:
                                states = ", ".join(f"{d.serial}: {d.state}" for d in devices)
                                raise RuntimeError("No device detected" if not devices else "Select exactly one authorized phone. " + states)
                            serial = current.serial if current else available[0].serial
                            detail = f"Discovery confirms authorized transport: {serial}"
                        elif key == "query":
                            state = self.adb.state(serial)
                            if state != "device":
                                raise RuntimeError(f"Phone is {state}")
                            detail = f"{serial}: Android {self.adb.android_version(serial)}; get-state=device"
                        elif key == "screenshot":
                            payload = self.adb.screenshot(serial)
                            width, height = png_dimensions(payload)
                            import cv2
                            import numpy as np
                            decoded = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
                            if decoded is None or decoded.shape[:2] != (height, width):
                                raise RuntimeError("Screenshot PNG could not be fully decoded")
                            detail = f"Decoded original-resolution screenshot: {width} × {height}; no pixels retained in report."
                        else:
                            status = self.streams.status(serial)
                            if status.state not in ("starting", "streaming"):
                                if status.state == "stopping":
                                    raise RuntimeError("Previous video session is still cleaning up; retry when stopped")
                                self.streams.start(serial)
                                owned_stream = True
                            deadline = time.monotonic() + self.video_timeout
                            while not self.cancel.is_set():
                                frame = self.streams.latest(serial)
                                if frame is not None and frame.serial == serial and time.monotonic() - frame.captured_at <= 3:
                                    detail = f"Received decoded RGB frame: {frame.width} × {frame.height}; source {frame.source_width} × {frame.source_height}."
                                    break
                                state = self.streams.status(serial)
                                if state.state == "failed":
                                    raise RuntimeError(state.error or "scrcpy failed before first frame")
                                if time.monotonic() >= deadline:
                                    raise RuntimeError("No fresh decoded frame before the video deadline")
                                self.cancel.wait(.05)
                            else:
                                raise RuntimeError("Video check cancelled")
                        step = DiagnosticStep(key, title, "passed", detail)
                    except Exception as error:
                        failed = True
                        step = DiagnosticStep(key, title, "failed", str(error)[:4000], SOLUTIONS[key])
                report.steps.append(step)
                self.progress(step)
        finally:
            if owned_stream and serial:
                self.streams.stop(serial)
        return report
