"""Real Qt + Monaco integration with explicitly injected fixture devices/video.

This test does not claim real-phone transport. Separate socket/H.264 tests cover
the actual transport/decoder; here fixtures isolate GUI/device ownership.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.devices.adb import DeviceInfo, ScreenInfo
from app.streaming.manager import StreamStatus
from app.streaming.session import VideoFrame
from app.ui import window as module
from app.vision.matching import Region


def spin(app, condition, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError("Workbench integration timed out")


def png(image):
    data = QByteArray()
    buffer = QBuffer(data)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(data)


class FixtureAdb:
    def __init__(self, executable):
        self.executable = executable
        self.observed = [DeviceInfo("fixture-one", "device"), DeviceInfo("fixture-two", "device")]
        self.actions = []
        rng = np.random.default_rng(73)
        pixels = rng.integers(0, 255, (200, 120, 3), dtype=np.uint8)
        self.image = QImage(pixels.tobytes(), 120, 200, 360, QImage.Format.Format_RGB888).copy()
        self.png = png(self.image)

    def devices(self):
        return list(self.observed)

    def state(self, serial):
        return next((device.state for device in self.observed if device.serial == serial), "disconnected")

    def android_version(self, serial):
        assert self.state(serial) == "device"
        return "fixture-Android"

    def screen_info(self, serial):
        return ScreenInfo(120, 200, 0)

    def screenshot(self, serial):
        assert serial in {d.serial for d in self.observed if d.available}
        return self.png

    def tap(self, serial, x, y):
        self.actions.append((serial, "tap", x, y))

    def swipe(self, serial, *points, duration_ms=500):
        self.actions.append((serial, "swipe", *points, duration_ms))

    def key(self, serial, key):
        self.actions.append((serial, "key", key))


class FixtureStreams:
    def __init__(self, adb):
        self.adb = adb
        self.frames = {}
        self.states = {}
        self.closed = False

    def start(self, serial, options):
        image = self.adb.image.scaled(60, 100).convertToFormat(QImage.Format.Format_RGB888)
        rows = np.frombuffer(image.constBits(), np.uint8).reshape(100, image.bytesPerLine())[:, :180]
        self.frames[serial] = VideoFrame(serial, rows.tobytes(), 60, 100, 120, 200, time.monotonic(), 1)
        self.states[serial] = StreamStatus("streaming", None, 1)

    def stop(self, serial):
        self.frames.pop(serial, None)
        if serial in self.states:
            self.states[serial] = StreamStatus("stopped")

    def latest(self, serial):
        return self.frames.get(serial)

    def status(self, serial):
        return self.states.get(serial, StreamStatus())

    def statuses(self):
        return dict(self.states)

    def close(self, timeout=0):
        self.closed = True
        self.frames.clear()
        return True


def main():
    directory = Path(sys.argv[1])
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    module.AdbClient = FixtureAdb
    module.StreamManager = FixtureStreams
    window = module.StudioWindow(discover=False)
    window._set_project(directory)
    window.preview_timer.stop()
    window.show()
    spin(app, lambda: window.editor.is_ready)
    window.refresh_devices()
    spin(app, lambda: window.devices.count() == 2 and not window.jobs)
    assert window.selected_serial() == "fixture-one"
    window.start_all_live()
    window._update_live_frames()
    assert window.preview.frame.serial == "fixture-one"
    tile = window.live_panel.tiles["fixture-two"][1]
    assert tile.frame.serial == "fixture-two"
    assert tile.frame.width == 60 and tile.viewport().source_width == 120
    # New tiles cause queued Qt layout/resize events. Those intentionally cancel
    # input begun with an obsolete transform; settle layout before the gesture.
    QTest.qWait(200)

    # A background tile targets its own serial, even while another row is selected.
    point = QPoint(*map(round, tile.viewport().from_device(30, 80)))
    QTest.mouseClick(tile, Qt.MouseButton.LeftButton, pos=point)
    try:
        spin(app, lambda: bool(window.adb.actions))
    except AssertionError:
        print(window.logs.toPlainText(), flush=True)
        raise
    assert window.adb.actions[-1][:2] == ("fixture-two", "tap")
    assert abs(window.adb.actions[-1][2] - 30) <= 1
    assert abs(window.adb.actions[-1][3] - 80) <= 1
    window._key("HOME")
    spin(app, lambda: any(a == ("fixture-one", "key", "HOME") for a in window.adb.actions))
    spin(app, lambda: not window.pending_controls)
    window._double_tap("fixture-two", tile, 20, 40)
    spin(app, lambda: len([a for a in window.adb.actions if a == ("fixture-two", "tap", 20, 40)]) == 2)
    spin(app, lambda: not window.pending_controls)

    window.capture_region()
    spin(app, lambda: bool(window._capture_dialogs))
    dialog = next(iter(window._capture_dialogs))
    assert dialog.serial == "fixture-one" and dialog.frame.size() == window.adb.image.size()
    dialog.select_region(Region(13, 24, 17, 19))
    saved = directory / "target ' téléphone.png"
    dialog.save_to(saved)
    import ast
    def has_reference():
        for node in ast.parse(window.editor.source).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "image_path":
                # Absolute references use native separators on Windows. Verify
                # the parsed Python literal resolves to the saved image.
                return Path(ast.literal_eval(node.value)).resolve() == saved.resolve()
        return False
    spin(app, has_reference)
    ast.parse(window.editor.source)
    assert QImage(str(saved)).size().width() == 17
    results = []
    dialog.match_finished.connect(results.append)
    dialog.start_match()
    spin(app, lambda: bool(results))
    assert results[0]["error"] is None and results[0]["matches"][0].region == Region(13, 24, 17, 19)
    dialog.reject()
    spin(app, lambda: not window._capture_dialogs)

    # Losing one phone clears only its preview and never redirects selection.
    window.adb.observed = [DeviceInfo("fixture-two", "device")]
    window.refresh_devices()
    spin(app, lambda: not window.discover_pending)
    assert window.registry.get("fixture-one").state == "disconnected"
    assert window.selected_serial() is None and window._selected_identity() == "fixture-one"
    assert window.preview.frame is None
    assert window.streams.status("fixture-two").state == "streaming"
    window.refresh_devices()
    spin(app, lambda: not window.discover_pending)
    assert window._selected_identity() == "fixture-one"
    before = list(window.adb.actions)
    window._control("fixture-one", lambda: window.adb.tap("fixture-one", 1, 2))
    app.processEvents()
    assert window.adb.actions == before

    def failed_discovery():
        raise RuntimeError("fixture ADB launch failed")
    window.adb.devices = failed_discovery
    window.refresh_devices()
    spin(app, lambda: not window.discover_pending)
    assert window.registry.get("fixture-two").state == "unknown"
    assert "fixture ADB launch failed" in window.device_manager.connection_status.text()
    assert "ADB discovery failed" in window.device_manager.summary.text()

    window.saved_source = window.editor.source  # Explicit test-only discard policy.
    window.close()
    spin(app, lambda: window._shutdown_complete)
    assert window.streams.closed and window.runtime.close(timeout=0)
    print(json.dumps({key: True for key in ("two_previews", "serial_control", "capture_monaco", "fresh_match", "disconnect", "discovery_error", "cleanup")}))


if __name__ == "__main__":
    main()
