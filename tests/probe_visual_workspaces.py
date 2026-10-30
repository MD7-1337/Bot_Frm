"""Real Qt/Monaco end-to-end panel interactions with clearly labeled fixture phones."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

from app.devices.adb import AdbError, DeviceInfo
from app.ui import window as module
from app.vision.matching import Region
from probe_device_workbench import FixtureAdb, FixtureStreams, spin


class NetworkFixtureAdb(FixtureAdb):
    def __init__(self, executable):
        super().__init__(executable)
        self.observed += [DeviceInfo("fixture-locked", "unauthorized"), DeviceInfo("fixture-offline", "offline")]
        self.network = []
        self.capture_threads = []
        self.gate = None
        self.capture_gate = None
        self.fail_disconnect = False

    def screenshot(self, serial):
        if self.capture_gate:
            assert self.capture_gate.wait(5)
        self.capture_threads.append(threading.get_ident())
        return super().screenshot(serial)

    def devices(self):
        if self.gate:
            assert self.gate.wait(5)
        return super().devices()

    def connect(self, endpoint):
        self.network.append(("connect", endpoint, threading.get_ident()))
        self.observed.append(DeviceInfo(endpoint, "device"))
        return f"Fixture transport connected: {endpoint}"

    def disconnect(self, endpoint):
        self.network.append(("disconnect", endpoint, threading.get_ident()))
        if self.fail_disconnect:
            raise AdbError("Fixture disconnect failure")
        self.observed = [device for device in self.observed if device.serial != endpoint]
        return f"Fixture transport disconnected: {endpoint}"


def button(panel, text):
    return next(widget for widget in panel.findChildren(QPushButton) if widget.text() == text)


def main():
    directory = Path(sys.argv[1])
    screenshots = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    (directory / "images").mkdir(exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    gui_thread = threading.get_ident()
    module.AdbClient = NetworkFixtureAdb
    module.StreamManager = FixtureStreams
    window = module.StudioWindow(discover=False)
    window._set_project(directory)
    window.preview_timer.stop()
    window.show()
    spin(app, lambda: window.editor.is_ready and not window.jobs)
    QTest.mouseClick(button(window.device_manager, "Refresh devices"), Qt.MouseButton.LeftButton)
    spin(app, lambda: window.devices.count() == 4 and not window.jobs)
    assert window.selected_serial() == "fixture-one"
    assert "2 connected / 4 known" in window.device_manager.summary.text()
    assert "120 × 200" in window.device_manager.details.text()

    # Navigation recovers a hidden dock. Selection made during discovery wins.
    window.docks["devices"].hide()
    QTest.keyClick(window, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    assert window.docks["devices"].isVisible()
    gate = threading.Event()
    window.adb.gate = gate
    window.refresh_devices()
    window.devices.setCurrentRow(1)
    window.devices.item(0).setSelected(True)
    gate.set()
    spin(app, lambda: not window.discover_pending and not window.jobs)
    window.adb.gate = None
    assert window._selected_identity() == "fixture-two"
    assert set(window._selected_phones()) == {"fixture-one", "fixture-two"}

    # Names/groups persist, do not replace ADB serials, and survive polling.
    window.device_manager.name.setText("Fixture phone TWO")
    window.device_manager.group.setText("Fixture group")
    QTest.mouseClick(button(window.device_manager, "Save name / group"), Qt.MouseButton.LeftButton)
    assert json.loads(window.settings.value("device_labels"))["fixture-two"]["group"] == "Fixture group"
    window.devices.setCurrentRow(0)
    window.device_manager.name.setText("Fixture phone ONE")
    window.device_manager.group.setText("Fixture group")
    window.device_manager.save_labels()
    window.device_manager.select_group()
    assert set(window._selected_phones()) == {"fixture-one", "fixture-two"}
    window.device_manager.name.setText("Unsaved name being edited")
    window.refresh_devices()
    spin(app, lambda: not window.discover_pending)
    assert set(window._selected_phones()) == {"fixture-one", "fixture-two"}
    assert window.device_manager.name.text() == "Unsaved name being edited"
    window.device_manager.name.setText("Fixture phone ONE")

    # An unauthorized selection must retain its identity without a routable phone.
    window.devices.setCurrentRow(2)
    spin(app, lambda: not window.jobs)
    assert window.selected_serial() is None and window._selected_identity() == "fixture-locked"
    assert "authorization dialog" in window.device_manager.details.text()
    window.devices.setCurrentRow(0)
    spin(app, lambda: not window.jobs)

    # Exact network endpoint; no host/transport calls run on the Qt GUI thread.
    window.device_manager.endpoint.setText("192.0.2.20:5555")
    QTest.mouseClick(button(window.device_manager, "Connect"), Qt.MouseButton.LeftButton)
    spin(app, lambda: window.devices.count() == 5 and not window.jobs)
    assert window.adb.network[0][:2] == ("connect", "192.0.2.20:5555")
    assert window.adb.network[0][2] != gui_thread
    window.devices.setCurrentRow(4)
    spin(app, lambda: not window.jobs)
    window.adb.fail_disconnect = True
    old_token = window._connection_token("192.0.2.20:5555")
    window.disconnect_device()
    spin(app, lambda: not window.jobs and not window.discover_pending)
    assert old_token.is_set()
    assert not window._connection_token("192.0.2.20:5555").is_set()
    assert window._preview_modes["192.0.2.20:5555"] == "stopped"
    window._key("HOME")
    spin(app, lambda: not window.pending_controls)
    assert window.adb.actions[-1] == ("192.0.2.20:5555", "key", "HOME")
    window.adb.fail_disconnect = False
    window.disconnect_device()
    spin(app, lambda: not window.jobs and not window.discover_pending)
    assert window.registry.get("192.0.2.20:5555").state == "disconnected"
    assert window._selected_identity() == "192.0.2.20:5555" and window.selected_serial() is None
    window.devices.setCurrentRow(0)
    spin(app, lambda: not window.jobs)

    # Test a previously saved library template against a new original capture.
    target = directory / "images" / 'target " téléphone.png'
    assert window.adb.image.copy(13, 24, 17, 19).save(str(target), "PNG")
    window.refresh_assets()
    spin(app, lambda: window.visual_tools.assets.count() == 1)
    window.visual_tools.assets.setCurrentRow(0)
    spin(app, lambda: not window.jobs)
    assert window.visual_tools.thumbnail.pixmap().isNull() is False
    window.visual_tools.offset.setText("2, -3")
    window.visual_tools.region.setText("0, 0, 120, 200")
    window.visual_tools.scales.setText("1, 1.25")
    window.editor.set_text("# Fixture workspace integration\n")
    window.insert_visual_command("click")
    spin(app, lambda: "targetOffset(2, -3)" in window.editor.source)
    assert ".atScales(1.0, 1.25)" in window.editor.source
    ast.parse(window.editor.source)
    window.visual_tools.scales.setText("1")
    window.test_asset()
    spin(app, lambda: bool(window._capture_dialogs))
    dialog = next(iter(window._capture_dialogs))
    assert dialog.template_image.size() == QImage(str(target)).size()
    results = []
    dialog.match_finished.connect(results.append)
    QTest.mouseClick(dialog.test_button, Qt.MouseButton.LeftButton)
    spin(app, lambda: bool(results))
    assert results[0]["error"] is None
    assert [match.region for match in results[0]["matches"]] == [Region(13, 24, 17, 19)]
    dialog.reject()
    spin(app, lambda: not window._capture_dialogs)

    # Capture must not migrate into a project selected while it was queued.
    gate = threading.Event()
    window.adb.capture_gate = gate
    window.capture_region()
    other_project = directory / "other-project"
    other_project.mkdir()
    window._set_project(other_project)
    gate.set()
    spin(app, lambda: not window.jobs)
    window.adb.capture_gate = None
    assert not window._capture_dialogs
    assert "active project or script changed" in window.logs.toPlainText()
    window._set_project(directory)
    spin(app, lambda: not window.jobs)

    # Saving while the preview is scaled must still capture full Android pixels.
    window.start_all_live()
    window._update_live_frames()
    assert window.preview.frame.width == 60
    saved = directory / "original.png"
    original_save = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = lambda *a, **k: (str(saved), "PNG")
    try:
        window.save_capture()
    finally:
        QFileDialog.getSaveFileName = original_save
    spin(app, lambda: saved.exists() and not window.jobs)
    assert QImage(str(saved)).size() == window.adb.image.size()
    assert all(thread != gui_thread for thread in window.adb.capture_threads)

    # Only the recorded serial's acknowledged manual controls enter its timeline.
    window.start_recording()
    window._key("HOME")
    spin(app, lambda: not window.pending_controls)
    assert window.recorder.actions == ["home()"]
    window._control("fixture-two", lambda: window.adb.tap("fixture-two", 4, 5), recorded="tap(4, 5)")
    spin(app, lambda: not window.pending_controls)
    assert window.recorder.actions == ["home()"]
    window.pause_recording()
    window._key("BACK")
    spin(app, lambda: not window.pending_controls)
    window.pause_recording()
    window._gesture_on("fixture-one", window.preview, (12, 23), (12, 23), 20)
    spin(app, lambda: not window.pending_controls)
    window.stop_recording()
    assert window.recorder.actions == ["home()", "tap(12, 23)"]
    window.recorder_panel.table.item(1, 0).setText("tap(30, 40)")
    window.recorder_panel.table.selectRow(1)
    window.recorder_panel.move_step(-1)
    window.insert_recording()
    spin(app, lambda: "tap(30, 40)" in window.editor.source)
    ast.parse(window.editor.source)
    assert window.recorder.actions == ["tap(30, 40)", "home()"]
    recorded_actions = list(window.recorder.actions)

    # One phone's loss stops its recorder; emergency stop invalidates another.
    window.recorder.start("fixture-one", window.registry.get("fixture-one").generation)
    window.recorder_panel.refresh(reset=True)
    window.adb.observed = [device for device in window.adb.observed if device.serial != "fixture-one"]
    window.refresh_devices()
    spin(app, lambda: not window.discover_pending)
    assert window.recorder.state == "stopped" and "disconnected" in window.recorder.reason
    window.devices.setCurrentRow(1)
    spin(app, lambda: not window.jobs)
    window.start_recording()
    assert window.recorder.state == "recording"
    window.emergency_stop()
    assert window.recorder.state == "stopped" and window.recorder.reason == "Emergency stop"

    # Explicit fixture screenshots for review, never Android hardware evidence.
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
        window.recorder.serial = "fixture-one"
        window.recorder.actions = recorded_actions
        window.recorder.reason = "Fixture controls captured by this probe; no Android input sent"
        window.recorder_panel.refresh(reset=True)
        window.visual_tools.assets.setCurrentRow(0)
        spin(app, lambda: not window.jobs)
        window.editor.set_text('# FIXTURE PHONES — no Android hardware connected\n' + window.visual_tools.code("click"))
        for name in ("devices", "visual", "recorder"):
            if name != "recorder":
                window.docks["events"].raise_()
            window.show_workspace(name)
            QTest.qWait(120)
            assert window.grab().save(str(screenshots / f"{name}-fixture.png"), "PNG")

    window.saved_source = window.editor.source
    window.close()
    spin(app, lambda: window._shutdown_complete)
    print(json.dumps({key: True for key in ("navigation", "selection", "groups", "network", "visual_library", "fresh_match", "full_resolution", "recorder", "disconnect", "cleanup")}))


if __name__ == "__main__":
    main()
