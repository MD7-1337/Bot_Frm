"""Visible-control journey through real Qt/Monaco and spawned fixture workers.

Synthetic phone/screens are labeled; this is never physical Android acceptance.
"""
from pathlib import Path
import json
import os
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QLineEdit, QMessageBox, QPushButton, QToolBar

from app.automation.qt_service import RuntimeService
from app.devices.adb import AdbClient as RealAdbClient, DeviceInfo, ScreenInfo
from app.streaming.manager import StreamStatus
from app.streaming.session import VideoFrame
from app.ui import window as module
from probe_device_workbench import FixtureAdb, FixtureStreams, png, spin


def click(panel, text):
    candidates = [button for button in panel.findChildren(QPushButton) if button.text() == text and button.isVisible()]
    assert candidates, f"No visible button: {text}"
    button = next((button for button in candidates if button.isEnabled()), candidates[0])
    assert button.isEnabled(), f"Disabled control: {text}"
    if not button.visibleRegion().contains(button.rect().center()):
        top = button.window()
        if screenshots := os.environ.get('STUDIO_SCREENSHOT_DIR'):
            directory = Path(screenshots)
            directory.mkdir(parents=True, exist_ok=True)
            top.grab().save(str(directory / f'clipped-{text.replace(" ", "-")}.png'))
        raise AssertionError(f"Clipped control: {text}; button={button.geometry().getRect()}; "
                             f"panel={panel.geometry().getRect()}; window={top.rect().getRect()}; "
                             f"position={button.mapTo(top, button.rect().center()).toTuple()}; "
                             f"visible={button.visibleRegion().boundingRect().getRect()}")
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def navigation(window, name):
    button = window.shell.nav[name]
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert window.shell.current == name
    QTest.qWait(40)


def toolbar(window, name):
    action = window.actions[name]
    bar = window.findChild(QToolBar, "contextToolbarV2")
    button = bar.widgetForAction(action)
    assert action.isEnabled() and button.isVisible(), f"Unavailable toolbar action {name}"
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


class AlphaAdb(FixtureAdb):
    def __init__(self, executable):
        super().__init__(executable)
        self.executable = sys.executable
        self.observed = [DeviceInfo("????????????", "no permissions")]
        self.calls = []
        self.image = QImage(320, 640, QImage.Format.Format_RGB32)
        self.image.fill(QColor("#14253e"))
        painter = QPainter(self.image)
        painter.setPen(QColor("#f4f7fc"))
        painter.setFont(QFont("DejaVu Sans", 13))
        painter.drawText(22, 38, "09:41      FIXTURE PHONE")
        painter.setFont(QFont("DejaVu Sans", 24))
        painter.drawText(22, 120, "Good morning")
        painter.setFont(QFont("DejaVu Sans", 12))
        painter.drawText(22, 155, "Synthetic • no Android device")
        painter.setBrush(QColor("#264466"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(22, 210, 276, 100, 16, 16)
        painter.setPen(QColor("#d4e7ff"))
        painter.drawText(42, 250, "Automation ready")
        painter.drawText(42, 280, "Review before running")
        painter.setBrush(QColor("#6ca7ff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(70, 350, 180, 54, 12, 12)
        painter.setPen(QColor("#10213e"))
        painter.setFont(QFont("DejaVu Sans", 14))
        painter.drawText(91, 385, "START SESSION")
        painter.end()
        self.png = png(self.image)

    def version(self):
        return "FIXTURE ADB — not physical transport"
    def start_server(self):
        self.calls.append(("server", threading.get_ident()))
    def device_listing(self):
        return "List of devices attached\n" + "\n".join(f"{d.serial} {d.state} model:{d.model or 'Fixture'}" for d in self.observed) + "\n"
    def screen_info(self, serial):
        return ScreenInfo(320, 640, 0)
    def connect(self, endpoint):
        self.observed.append(DeviceInfo(endpoint, "unauthorized"))
        return "Transport acknowledged; authorization remains unverified"

    def pair(self, endpoint, code):
        assert code == "123456"
        self.calls.append(("pair", endpoint, threading.get_ident()))
        return "Fixture pairing acknowledged; connection still required"

    def disconnect(self, endpoint):
        self.observed = [device for device in self.observed if device.serial != endpoint]
        return f"Fixture transport disconnected: {endpoint}"


class AlphaStreams(FixtureStreams):
    def start(self, serial, options=None):
        self.states[serial] = StreamStatus("streaming", None, 1)
    def latest(self, serial):
        if self.states.get(serial, StreamStatus()).state != "streaming":
            return None
        image = self.adb.image.convertToFormat(QImage.Format.Format_RGB888)
        rows = np.frombuffer(image.constBits(), np.uint8).reshape(640, image.bytesPerLine())[:, :960]
        state = self.states[serial]
        self.states[serial] = StreamStatus("streaming", None, state.frames + 1)
        return VideoFrame(serial, rows.tobytes(), 320, 640, 320, 640, time.monotonic(), state.frames + 1, 0)


def select(window, serial):
    for row in range(window.devices.count()):
        if window.devices.item(row).data(Qt.ItemDataRole.UserRole).serial == serial:
            window.devices.setCurrentRow(row)
            return
    raise AssertionError(f"Device row absent: {serial}")


def main():
    directory = Path(sys.argv[1])
    screenshots = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    (directory / "images").mkdir(exist_ok=True)
    (directory / "scripts").mkdir(exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    module.AdbClient = AlphaAdb
    module.StreamManager = AlphaStreams
    frame_path = directory / "fixture-screen.png"
    class FixtureService(RuntimeService):
        def start(self, source, serial, **kwargs):
            assert kwargs.pop("backend") == "adb"
            return super().start(source, serial, backend="mock", mock_config={"frame_paths": [str(frame_path)]}, **kwargs)
    module.RuntimeService = FixtureService
    window = module.StudioWindow(discover=False)
    window._set_project(directory)
    frame_path.write_bytes(window.adb.png)
    window.preview_timer.stop()
    window.show()
    events = []
    window.runtime.event.connect(events.append)
    original_warning = QMessageBox.warning
    original_question = QMessageBox.question
    QMessageBox.warning = lambda *a, **k: QMessageBox.StandardButton.Yes
    QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
    original_open = QFileDialog.getOpenFileName
    original_save = QFileDialog.getSaveFileName
    original_input = QInputDialog.getText
    try:
        spin(app, lambda: window.editor.is_ready and not window.jobs)
        window._sync_controls()
        assert not window.run_action.isEnabled() and not window.live_panel.start_button.isEnabled()
        navigation(window, "devices")
        click(window.device_manager, "Diagnose Connection")
        spin(app, lambda: not window._diagnostic_busy and window.device_manager.report is not None)
        assert window.device_manager.report.steps[4].state == "failed"
        assert "no permissions" in window.device_manager.report.steps[4].detail
        click(window.device_manager, "Copy Diagnostic Report")
        copied = QApplication.clipboard().text()
        assert "NOT VERIFIED" in copied and "????????????" not in copied and "udev" in copied
        assert window.adb.calls[0][1] != threading.get_ident()

        window.device_manager.tabs.setCurrentIndex(0)
        window.device_manager.endpoint.setText("192.0.2.50:37123")
        QInputDialog.getText = lambda *a, **k: ("123456", True)
        click(window.device_manager, "Pair…")
        spin(app, lambda: not window.jobs and not window.discover_pending)
        assert any(call[0] == "pair" for call in window.adb.calls)
        assert "123456" not in window.logs.toPlainText() + window.device_manager.history.toPlainText()
        click(window.device_manager, "Connect")
        spin(app, lambda: not window.jobs and not window.discover_pending)
        assert "unauthorized" in window._connection_problem
        select(window, "192.0.2.50:37123")
        click(window.device_manager, "Disconnect selected Wi-Fi")
        spin(app, lambda: not window.jobs and not window.discover_pending)
        assert window.registry.get("192.0.2.50:37123").state == "disconnected"

        # A USB cable becoming accessible is represented only by an explicit fixture update.
        window.adb.observed = [DeviceInfo("fixture-alpha-one", "device", "Fixture One"), DeviceInfo("fixture-alpha-two", "device", "Fixture Two")]
        click(window.device_manager, "Refresh devices")
        spin(app, lambda: not window.jobs and not window.discover_pending)
        select(window, "fixture-alpha-one")
        spin(app, lambda: not window.jobs)
        window._sync_controls()
        click(window.device_manager, "Open preview")
        spin(app, lambda: window.preview.frame is not None and window._preview_modes.get("fixture-alpha-one") == "live")
        QTest.qWait(200)  # settle the new preview tile/geometry before beginning a gesture
        preview = window.preview
        point = QPoint(*map(round, preview.viewport().from_device(40, 100)))
        QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
        spin(app, lambda: any(action[:2] == ("fixture-alpha-one", "tap") for action in window.adb.actions))
        tap = next(action for action in window.adb.actions if action[:2] == ("fixture-alpha-one", "tap"))
        assert abs(tap[2] - 40) <= 1 and abs(tap[3] - 100) <= 1, tap

        navigation(window, "visual")
        window._sync_controls()
        click(window.visual_tools, "Capture region…")
        spin(app, lambda: bool(window._capture_dialogs))
        dialog = next(iter(window._capture_dialogs))
        QTest.qWait(100)
        start = QPoint(*map(round, dialog.canvas.viewport().from_device(70, 350)))
        end = QPoint(*map(round, dialog.canvas.viewport().from_device(249, 403)))
        QTest.mousePress(dialog.canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(dialog.canvas, end)
        QTest.mouseRelease(dialog.canvas, Qt.MouseButton.LeftButton, pos=end)
        assert dialog.selected_region is not None and dialog.selected_region.width > 170
        target = directory / "images/start.png"
        QFileDialog.getSaveFileName = lambda *a, **k: (str(target), "PNG")
        click(dialog, "Save crop + insert reference…")
        spin(app, lambda: target.exists() and "image_path =" in window.editor.source)
        matched = []
        dialog.match_finished.connect(matched.append)
        click(dialog, "Test match on fresh frame")
        spin(app, lambda: bool(matched))
        assert matched[0]["error"] is None and len(matched[0]["matches"]) == 1
        dialog.reject()
        spin(app, lambda: not window._capture_dialogs and not window.jobs)
        assert window.visual_tools.assets.count() == 1
        window.visual_tools.assets.setCurrentRow(0)
        spin(app, lambda: not window.jobs)

        navigation(window, "studio")
        source = 'click("start.png")\nprint("alpha-journey")\nwhile True:\n    sleep(.05)\n'
        window.editor.set_text(source)
        QTest.qWait(100)
        script = directory / "scripts/journey.py"
        QFileDialog.getSaveFileName = lambda *a, **k: (str(script), "Python")
        toolbar(window, "save")
        assert script.read_bytes().decode("utf-8") == source
        window._sync_controls()
        toolbar(window, "run")
        spin(app, lambda: any(e.get("command") == "tap" for e in events))
        spin(app, lambda: bool(window.run_states) and window.run_states[-1].state == "running")
        toolbar(window, "pause")
        spin(app, lambda: window.run_states[-1].state == "paused")
        toolbar(window, "resume")
        spin(app, lambda: window.run_states[-1].state == "running")
        toolbar(window, "stop")
        spin(app, lambda: window.run_states[-1].exitcode is not None)
        assert window.run_states[-1].state == "cancelled"
        assert {e["serial"] for e in events if e.get("command") == "tap"} == {"fixture-alpha-one"}

        navigation(window, "recorder")
        spin(app, lambda: not window.pending_controls)
        window._sync_controls()
        click(window.recorder_panel, "Start on current phone")
        point = QPoint(*map(round, preview.viewport().from_device(40, 100)))
        QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
        spin(app, lambda: bool(window.recorder.actions) and not window.pending_controls)
        click(window.live_panel, "Home")
        spin(app, lambda: len(window.recorder.actions) >= 2 and not window.pending_controls)
        click(window.recorder_panel, "Stop recording")
        window._sync_controls()
        window.recorder_panel.delay.setValue(.02)
        click(window.recorder_panel, "Add delay")
        session = directory / "recording.json"
        QFileDialog.getSaveFileName = lambda *a, **k: (str(session), "JSON")
        click(window.recorder_panel, "Save session…")
        assert json.loads(session.read_text())["actions"]
        QFileDialog.getOpenFileName = lambda *a, **k: (str(session), "JSON")
        click(window.recorder_panel, "Open session…")
        assert window.recorder.state == "stopped"
        before = len(window.run_states)
        window._sync_controls()
        click(window.recorder_panel, "Replay on selected phone…")
        spin(app, lambda: len(window.run_states) > before and window.run_states[-1].exitcode is not None)
        assert window.run_states[-1].state == "completed"

        # Tabs preserve unsaved source; reopening a file selects its existing buffer.
        navigation(window, "studio")
        window.new_script()
        window.editor.set_text("# unsaved tab\nvalue = 42\n")
        QTest.qWait(80)
        window.shell.documents.remember()
        index = window.shell.documents.current
        window.open_script_path(script)
        QTest.qWait(80)
        assert window.path == script
        window.shell.documents.bar.setCurrentIndex(index)
        QTest.qWait(80)
        assert "value = 42" in window.editor.source and window.path is None

        navigation(window, "settings")
        panel = window.shell.settings_panel
        panel.adb_path.setText(str(directory / "missing-adb"))
        click(panel, "Apply settings")
        assert "Stop live previews" in panel.result.text()
        panel.adb_path.setText("")
        panel.theme.setCurrentText("light")
        panel.font_size.setValue(16)
        click(panel, "Apply settings")
        assert window.settings.value("theme") == "light"
        appearance = []
        window.editor.page.runJavaScript("window.studio.editor.getOption(monaco.editor.EditorOption.fontSize)", appearance.append)
        spin(app, lambda: bool(appearance))
        assert appearance[0] == 16
        panel.theme.setCurrentText("dark")
        click(panel, "Apply settings")

        palette_used = []
        def choose_settings():
            dialog = QApplication.activeModalWidget()
            assert dialog is not None
            search = dialog.findChild(QLineEdit)
            search.setText("Settings")
            QTest.keyClick(search, Qt.Key.Key_Return)
            palette_used.append(True)
        window.activateWindow()
        window.shell.command_button.setFocus()
        QTest.qWait(50)
        QTimer.singleShot(80, choose_settings)
        QTest.keyClick(window, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        spin(app, lambda: bool(palette_used))
        assert palette_used and window.shell.current == "settings"

        # Inspect real rendered layouts at desktop/laptop sizes, including compact preview access.
        for width, height in ((1440, 900), (1100, 760), (1024, 700)):
            window.resize(width, height)
            QTest.qWait(150)
            assert window.width() <= width, (width, window.width())
            for name in ("studio", "devices", "visual", "recorder", "settings"):
                navigation(window, name)
                assert window.shell.emergency.isVisible() and window.shell.emergency.visibleRegion().contains(window.shell.emergency.rect().center())
                assert window.shell.nav[name].isVisible()
        window.resize(1440, 900)
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            window.diagnose_connection()
            spin(app, lambda: not window._diagnostic_busy)
            window.shell.notification.setText("FIXTURE DIAGNOSTICS — staged workflow exercised with injected devices; no Android hardware")
            window.shell.notification.show()
            QTest.qWait(100)
            window.grab().save(str(screenshots / "alpha-diagnostics.png"), "PNG")
            window.device_manager.tabs.setCurrentIndex(0)
            window.editor.set_text('# FIXTURE phone • verify on your own device before running\nclick(Pattern("start.png").similar(0.9))\ncolor = getPixel(40, 100)\nprint(device.serial, color)\n')
            for name in ("studio", "devices", "visual", "recorder", "settings", "monitor"):
                navigation(window, name)
                window.shell.notification.setText("FIXTURE PHONES / SYNTHETIC SCREENS — no Android hardware connected in this validation")
                window.shell.notification.show()
                QTest.qWait(150)
                assert window.grab().save(str(screenshots / f"alpha-{name}.png"), "PNG")
            navigation(window, "devices")
            window.shell.reveal_preview()
            window.shell.notification.setText("FIXTURE PHONE PREVIEW — synthetic screen; real scrcpy is validated separately with codec/socket tests")
            window.shell.notification.show()
            QTest.qWait(100)
            window.grab().save(str(screenshots / "alpha-preview.png"), "PNG")
            window.resize(1024, 700)
            window.shell.preview_on_small = False
            navigation(window, "studio")
            window.shell.notification.setText("COMPACT 1024 × 700 / FIXTURE — use Preview to reveal the phone")
            window.shell.notification.show()
            QTest.qWait(150)
            window.grab().save(str(screenshots / "alpha-compact.png"), "PNG")
            for name in ("devices", "visual", "recorder", "settings"):
                navigation(window, name)
                window.shell.notification.setText("COMPACT 1024 × 700 / FIXTURE — no Android hardware")
                window.shell.notification.show()
                QTest.qWait(100)
                window.grab().save(str(screenshots / f"alpha-{name}-compact.png"), "PNG")

        # Rebind a real adapter to a missing path while idle; GUI diagnostics must
        # show a real executable failure, not a fixture success or silent fallback.
        for serial in list(window.streams.statuses()):
            window.streams.stop(serial)
        spin(app, lambda: not window.jobs)
        navigation(window, "settings")
        module.AdbClient = RealAdbClient
        window.shell.settings_panel.adb_path.setText(str(directory / "missing-adb"))
        click(window.shell.settings_panel, "Apply settings")
        spin(app, lambda: not window.jobs and not window.discover_pending)
        assert window.adb.executable.endswith("missing-adb")
        window.diagnose_connection()
        spin(app, lambda: not window._diagnostic_busy)
        assert window.device_manager.report.steps[0].state == "failed"
        window.shell.documents.remember()
        dirty_count = sum(document.source != document.saved for document in window.shell.documents.documents)
        discard_prompts = []
        normal_question = QMessageBox.question
        def discard_once(*args, **kwargs):
            discard_prompts.append(True)
            return QMessageBox.StandardButton.Discard
        QMessageBox.question = discard_once
        assert window._confirm_all_documents()
        assert len(discard_prompts) == dirty_count
        QMessageBox.question = normal_question
        for document in window.shell.documents.documents:
            document.saved = document.source
        window.saved_source = window.editor.source
        window.close()
        spin(app, lambda: window._shutdown_complete)
        print(json.dumps({key: True for key in ("permissions_diagnostics", "visible_controls", "preview", "capture_crop_insert_match", "script_run_pause_stop", "recorder_session_replay", "tabs", "themes", "responsive", "cleanup")}))
    finally:
        QMessageBox.warning, QMessageBox.question = original_warning, original_question
        QFileDialog.getOpenFileName, QFileDialog.getSaveFileName = original_open, original_save
        QInputDialog.getText = original_input
        if not window._shutdown_complete:
            for document in window.shell.documents.documents:
                document.saved = document.source
            window.saved_source = window.editor.source
            window.close()
            spin(app, lambda: window._shutdown_complete)


if __name__ == "__main__":
    main()
