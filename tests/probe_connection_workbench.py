"""Real native window + Monaco, with explicitly declared hardware observations."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidgetItem, QPushButton, QWizard

from app.devices.adb import DeviceInfo
from app.devices.diagnostics import DiagnosticReport, DiagnosticStep
from app.streaming.session import VideoFrame
from app.ui.window import StudioWindow


def spin(app, condition, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError("Connection workbench integration timed out")


def main(root, screenshots=None):
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = StudioWindow(discover=False)
    window.resize(1024, 700)
    window.show()
    spin(app, lambda: window.editor.is_ready and not window.jobs)
    window.control_timer.stop()
    window.preview_timer.stop()
    window.stream_timer.stop()
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Stale wizard input reached ADB")
    window.adb.key = window.adb.tap = window.adb.swipe = forbidden
    window.show_workspace("devices")
    control = next(button for button in window.device_manager.findChildren(QPushButton)
                   if button.text() == "Connection wizard…")
    assert control.isVisible() and control.isEnabled()
    QTest.mouseClick(control, Qt.MouseButton.LeftButton)
    wizard = window._connection_wizard
    assert wizard.isVisible() and not wizard.isModal() and not wizard.discovery_page.isComplete()

    device = window.registry.update([DeviceInfo("FIXTURE-USB", "device", "TEST FIXTURE - no hardware")])[0]
    item = QListWidgetItem(window.device_manager.caption(device))
    item.setData(Qt.ItemDataRole.UserRole, device)
    window.devices.addItem(item)
    window.devices.setCurrentItem(item)
    window.device_manager.update_devices([device])
    window._apply_device_states([device])
    report = DiagnosticReport("fixture-adb", serials=[device.serial], verified_serial=device.serial)
    report.steps.append(DiagnosticStep("query", "Harmless query fixture", "passed", "Declared fixture result; NOT physical phone evidence"))
    window.device_manager.set_report(report)
    token = window._connection_token(device.serial)
    window._diagnostic_connection = token
    window._preview_modes[device.serial] = "live"
    # This is a decoded-frame-shaped fixture supplied to the host observation
    # boundary, not a real scrcpy socket/decoder or hardware validation.
    window.streams.latest = lambda serial: VideoFrame(serial, b"\x00" * 18, 2, 3, 2, 3, time.monotonic(), 1)
    window._sync_connection_wizard()
    assert wizard.discovery_page.isComplete() and wizard.verify_page.isComplete() and wizard.preview_page.isComplete()
    QTest.mouseClick(wizard.prepared, Qt.MouseButton.LeftButton, pos=QPoint(8, wizard.prepared.height() // 2))
    for _ in range(3):
        QTest.mouseClick(wizard.button(QWizard.WizardButton.NextButton), Qt.MouseButton.LeftButton)
    assert wizard.currentId() == 3 and wizard.home_button.isEnabled()
    # Simulate a connection change after the UI was enabled, before its queued
    # user intent is handled. The host must revalidate, not trust widget state.
    token.set()
    QTest.mouseClick(wizard.home_button, Qt.MouseButton.LeftButton)
    spin(app, lambda: "same idle verified" in window.logs.toPlainText())
    assert not calls and not window.pending_controls
    window._sync_connection_wizard()
    assert not wizard.home_button.isEnabled() and not wizard.verify_page.isComplete()
    wizard.restart()
    wizard.resize(700, 600)
    QTest.qWait(50)
    assert wizard.width() <= 760
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
        tag = "125" if app.devicePixelRatio() > 1.1 else "100"
        wizard.grab().save(str(screenshots / f"connection-wizard-compact-{tag}.png"))
    wizard.hide()
    for workspace in ("studio", "devices", "visual", "recorder", "debugger", "tasks", "projects", "monitor", "settings"):
        window.show_workspace(workspace)
        # Reparented WebEngine widgets need a rendering turn, particularly
        # with fractional scaling in an offscreen software-rendered process.
        QTest.qWait(200)
        assert window.width() <= 1024, (workspace, window.width())
        emergency = window.shell.emergency
        assert emergency.visibleRegion().contains(emergency.rect().center()), workspace
        if workspace == "debugger":
            observed_source = []
            window.editor.page.runJavaScript("window.studio.getText()", observed_source.append)
            spin(app, lambda: bool(observed_source))
            assert observed_source[0] == window.editor.source and observed_source[0].strip()
        if screenshots and workspace in ("tasks", "projects", "debugger"):
            window.grab().save(str(screenshots / f"{workspace}-compact-{tag}.png"))
    wizard.show()
    window.close()
    spin(app, lambda: window._shutdown_complete)
    assert not wizard.isVisible() and not calls
    print(json.dumps({"scale_factor": app.devicePixelRatio(), **{key: True for key in
        ("monaco_ready", "central_wizard", "report_generation", "stale_home_rejected", "compact_workspaces", "wizard_cleanup")}}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
