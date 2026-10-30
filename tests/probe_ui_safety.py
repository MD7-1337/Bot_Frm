"""Subprocess GUI regression probe; uses real Qt widgets and explicit test data."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.automation.runtime import RunInfo
from app.devices.adb import DeviceInfo
from app.streaming.capture import ScreenFrame
from app.ui import window as window_module


class TestEditor(QWidget):
    """Avoid starting another browser for tests of device/UI state ownership."""
    error = Signal(str)
    document_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.source = ""
        self.is_ready = True
        self.stopped = False

    def set_text(self, source):
        self.source = source

    def shutdown(self):
        self.stopped = True

    def set_project_root(self, root, script_dir=None):
        self.project_root = root

    def set_execution_line(self, line):
        self.execution_line = line

    def set_run_status(self, status):
        self.run_status = status


def spin(application, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Qt completion callback timed out")


def frame(width, height, serial="PHONE1"):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#1a70bc"))
    data = QByteArray()
    buffer = QBuffer(data)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return ScreenFrame(serial, bytes(data), width, height, time.monotonic())


def main():
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    window_module.EditorWidget = TestEditor
    window = window_module.StudioWindow(discover=False)
    window.registry.update([DeviceInfo("PHONE1", "device"), DeviceInfo("PHONE2", "device")])
    window.preview_timer.stop()
    window.show()
    application.processEvents()

    # A stale snapshot of a prior run must not release the newly pending lease.
    old = RunInfo("old", "PHONE1", "script", "mock", "completed", 1, 0)
    window.pending_runs["request-new"] = "PHONE1"
    window._runtime_snapshot([old])
    assert window.pending_runs == {"request-new": "PHONE1"} and window.busy("PHONE1")
    window._runtime_event({"event": "request", "command": "start", "request_id": "request-new", "run_id": "new"})
    window._runtime_snapshot([old])
    window._runtime_snapshot([old])
    assert window.pending_runs == {"request-new": "PHONE1"}
    current = RunInfo("new", "PHONE1", "script", "mock", "running", 2, None)
    window._runtime_snapshot([old, current])
    assert not window.pending_runs and not window.pending_run_ids and window.busy("PHONE1")
    window._runtime_snapshot([old, replace(current, state="completed", exitcode=0)])
    assert not window.busy("PHONE1")
    window.pending_runs["bad"] = "PHONE1"
    window._runtime_event({"event": "request_error", "request_id": "bad"})
    assert not window.pending_runs

    # Emergency stop prevents new manual inputs and invalidates already queued
    # input even when the stop is later reset before the thread dispatches it.
    queued = []
    original_submit = window._submit
    window._submit = lambda operation, callback: queued.append((operation, callback))
    actions = []
    window._control("PHONE1", lambda: actions.append("tap"))
    assert len(queued) == 1
    window.emergency_stop()
    window._control("PHONE2", lambda: actions.append("home"))
    assert len(queued) == 1 and not actions
    window._runtime_event({"event": "request", "command": "reset_emergency_stop"})
    try:
        queued[0][0]()
    except RuntimeError as error:
        assert "cancelled" in str(error)
    else:
        raise AssertionError("Queued control survived its emergency stop generation")
    queued[0][1](None, "cancelled")
    assert not actions and not window.pending_controls
    window._control("PHONE1", lambda: actions.append("fresh"))
    queued[1][0]()
    queued[1][1](None, None)
    assert actions == ["fresh"]
    window._submit = original_submit

    # Real PNG decode/rendering and synthetic pointer events exercise the widget.
    preview = window.preview
    preview.set_frame(frame(100, 200))
    assert preview.image.width() == 100 and preview.image.height() == 200
    gestures = []
    preview.gesture.connect(lambda start, end, duration: gestures.append((start, end)))
    window.preview.gesture.disconnect(window._gesture)
    point = QPoint(*map(round, preview.viewport().from_device(25, 50)))
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
    assert preview._press is not None
    preview.set_frame(frame(200, 100))
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
    assert not gestures and preview._press is None
    point = QPoint(*map(round, preview.viewport().from_device(40, 30)))
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    spin(application, lambda: bool(gestures))
    assert len(gestures) == 1 and gestures[0][0] == gestures[0][1]
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
    preview.set_frame(frame(200, 100, serial="PHONE2"))
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
    assert len(gestures) == 1

    # Operations run on pool threads; completion callbacks run on the GUI thread.
    gui_thread = threading.get_ident()
    completions = []
    window._submit(lambda: threading.get_ident(), lambda result, error: completions.append((result, threading.get_ident(), error)))
    spin(application, lambda: bool(completions))
    assert completions[0][0] != gui_thread
    assert completions[0][1] == gui_thread and completions[0][2] is None
    assert not window.jobs

    # Shutdown defers exit while a job runs, keeps Qt processing, and never calls
    # its UI completion after closing has started.
    gate = threading.Event()
    late_callbacks = []
    window._submit(lambda: gate.wait(2), lambda *args: late_callbacks.append(args))
    started = time.monotonic()
    window.close()
    assert time.monotonic() - started < 0.2
    assert window._closing and not window._shutdown_complete
    gate.set()
    spin(application, lambda: window._shutdown_complete)
    application.processEvents()
    assert window.editor.stopped and not late_callbacks
    assert window.runtime.close(timeout=0)
    print(json.dumps({"leases": True, "emergency_manual": True, "preview_png_gestures": True,
                      "job_gui_thread": True, "shutdown": True}))


if __name__ == "__main__":
    main()
