"""Actual native controls, local Monaco, SQLite and spawned simulator workers.

Qt file/trust dialogs are driven through their widgets, not replaced. No real
phone, Windows runtime, transport or packaged executable is exercised here.
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QInputDialog, QLineEdit, QMessageBox

from app.projects.management import ProjectStore
from app.ui.capture_dialog import CaptureDialog
from app.ui.task_panel import TaskDialog
from app.ui.window import StudioWindow
from app.vision.matching import Region
from probe_alpha_ux import click, navigation


def spin(application, condition, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError("Alpha workflow timed out")


class DialogDriver:
    def __init__(self, application):
        self.application = application
        self.actions = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(20)
        self.error = None
        self._last_modal = None
        self._driven_modal = None

    def expect(self, kind, callback):
        self.actions.append((kind, callback))

    def tick(self):
        modal = self.application.activeModalWidget()
        if modal is not None and modal is not self._last_modal:
            self._last_modal = modal
            print(f"Modal {type(modal).__name__}: {modal.windowTitle()}", flush=True)
        # A filename action finishes after the asynchronous directory model has
        # settled. Until that same dialog closes, do not consume the next queue
        # item (which may also expect a QFileDialog, such as import destination).
        if self.actions and modal is not self._driven_modal and isinstance(modal, self.actions[0][0]):
            _, callback = self.actions.pop(0)
            self._driven_modal = modal
            try:
                print(f"Driving {type(modal).__name__}: {modal.windowTitle()}", flush=True)
                callback(modal)
            except Exception as error:
                self.error = error
                modal.reject()

    def directory(self, root):
        def select(dialog):
            dialog.setDirectory(str(root))
            dialog.accept()
        self.expect(QFileDialog, select)

    def filename(self, path):
        def select(dialog):
            dialog.setDirectory(str(path.parent))
            # QFileSystemModel loads the chosen directory asynchronously.
            # Selecting/accepting in the same callback can retain the dialog's
            # original "script.py" filename. Drive the visible filename control
            # after the directory change has reached its event loop instead.
            def enter_name():
                field = dialog.findChild(QLineEdit, "fileNameEdit")
                if field is None:
                    self.error = AssertionError("Save dialog filename control is unavailable")
                    dialog.reject()
                    return
                field.setText(path.name)
                dialog.accept()
            QTimer.singleShot(150, enter_name)
        self.expect(QFileDialog, select)

    def text(self, value):
        def fill(dialog):
            dialog.setTextValue(value)
            dialog.accept()
        self.expect(QInputDialog, fill)

    def trust_python(self):
        self.expect(QMessageBox, lambda dialog: dialog.button(QMessageBox.StandardButton.Yes).click())


def main(root, screenshots):
    root.mkdir(parents=True, exist_ok=True)
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    dialogs = DialogDriver(application)
    window = StudioWindow(discover=False)
    window.resize(1520, 1040)
    window.show()
    spin(application, lambda: window.editor.is_ready and not window.jobs)
    checks = {}
    events = []
    window.runtime.event.connect(events.append)
    native_calls = []
    def forbidden(*args, **kwargs):
        native_calls.append(args)
        raise AssertionError("Simulation crossed into ADB")
    window.adb.tap = window.adb.swipe = window.adb.key = window.adb.screenshot = forbidden

    # Create through the real project panel, including its native chooser/input.
    navigation(window, "projects")
    dialogs.directory(root)
    dialogs.text("managed-workflow")
    click(window.project_panel, "New project…")
    managed = root / "managed-workflow"
    spin(application, lambda: window.project_panel.store is not None and not window.project_panel.busy)
    assert window.project_root == managed
    checks["managed_project"] = (managed / "project.json").is_file()

    navigation(window, "devices")
    window.device_manager.tabs.setCurrentWidget(window.simulation_panel)
    click(window.simulation_panel, "Start Demo Session")
    spin(application, lambda: window.active_simulation is not None and window.preview.frame is not None and not window._demo_pending)
    serial = window.active_simulation
    navigation(window, "projects")
    dialogs.directory(managed)
    click(window.project_panel, "Open project…")
    spin(application, lambda: window.project_root == managed and not window.project_panel.busy)
    navigation(window, "studio")
    window.actions["new"].trigger()
    QTest.qWait(50)
    assert window.path is None

    # Crop a genuine simulator screenshot into the selected managed project.
    window.actions["capture"].trigger()
    spin(application, lambda: any(isinstance(dialog, CaptureDialog) for dialog in window._capture_dialogs))
    capture = next(dialog for dialog in window._capture_dialogs if isinstance(dialog, CaptureDialog))
    capture.select_region(Region(60, 480, 240, 64))
    dialogs.filename(managed / "images" / "start.png")
    click(capture, "Save crop + insert reference…")
    spin(application, lambda: (managed / "images" / "start.png").exists())
    capture.reject()
    spin(application, lambda: capture not in window._capture_dialogs)
    checks["captured_target"] = True

    source = 'counter = 40\ncounter += 2\nhome()\nclick("start.png")\nprint("scheduled-and-debugged", counter)\n'
    window.editor.set_text(source)
    def js(expression):
        result = []
        window.editor.page.runJavaScript(expression, result.append)
        spin(application, lambda: bool(result))
        return result[0]
    spin(application, lambda: js("window.studio.getText()") == source)
    script = managed / "scripts" / "main.py"
    dialogs.filename(script)
    window.actions["save"].trigger()
    print(f"Saved path: {window.path}", flush=True)
    try:
        spin(application, lambda: window.path == script and script.exists())
    except AssertionError as error:
        raise AssertionError({"path": str(window.path), "expected": str(script), "exists": script.exists(),
                              "dialogs": len(dialogs.actions), "dialog_error": str(dialogs.error),
                              "logs": window.logs.toPlainText()[-3000:]}) from error

    # A genuine Qt pointer event in Monaco's glyph margin sets the breakpoint.
    coords = json.loads(js("JSON.stringify((()=>{const e=window.studio.editor;const r=e.getDomNode().getBoundingClientRect();const p=e.getScrolledVisiblePosition({lineNumber:2,column:1});const l=e.getLayoutInfo();return {x:r.left+l.glyphMarginLeft+l.glyphMarginWidth/2,y:r.top+p.top+p.height/2};})())"))
    QTest.mouseClick(window.editor.view.focusProxy() or window.editor.view,
                     Qt.MouseButton.LeftButton, pos=QPoint(round(coords["x"]), round(coords["y"])))
    spin(application, lambda: window.editor.breakpoints == [2])
    checks["gutter_breakpoint"] = True
    navigation(window, "debugger")
    dialogs.trust_python()
    click(window.debugger_panel, "Debug trusted script…")
    spin(application, lambda: any(event.get("event") == "debug_stopped" and event.get("line") == 2 for event in events))
    stopped = [event for event in events if event.get("event") == "debug_stopped"][-1]
    assert next(item for item in stopped["locals"] if item["name"] == "counter")["value"] == "40"
    assert window.debugger_panel.variables.topLevelItemCount() == 2
    checks["debug_variables"] = True
    click(window.debugger_panel, "Step over")
    spin(application, lambda: any(event.get("event") == "debug_stopped" and event.get("line") == 3 for event in events))
    stopped = [event for event in events if event.get("event") == "debug_stopped"][-1]
    assert next(item for item in stopped["locals"] if item["name"] == "counter")["value"] == "42"
    checks["debug_step"] = True
    if screenshots:
        QTest.qWait(100)
        window.grab().save(str(screenshots / "debugger-variables.png"))
    click(window.debugger_panel, "Continue")
    spin(application, lambda: bool(window.run_states) and window.run_states[-1].exitcode is not None)
    assert window.run_states[-1].state == "completed", events
    assert window.simulations.client(serial).state()["screen"] == "dashboard"

    # Record real studio Home/tap controls, then schedule their generated Python.
    navigation(window, "recorder")
    spin(application, lambda: window.recorder_panel.buttons["Start on current phone"].isEnabled())
    click(window.recorder_panel, "Start on current phone")
    click(window.live_panel, "Home")
    spin(application, lambda: window.simulations.client(serial).state()["screen"] == "start" and not window.pending_controls)
    QTest.qWait(200)
    point = QPoint(*map(round, window.preview.viewport().from_device(180, 512)))
    QTest.mouseClick(window.preview, Qt.MouseButton.LeftButton, pos=point)
    spin(application, lambda: window.simulations.client(serial).state()["screen"] == "dashboard" and not window.pending_controls)
    click(window.recorder_panel, "Stop recording")
    spin(application, lambda: window.recorder_panel.buttons["Insert Python into Monaco"].isEnabled())
    generated = window.recorder_panel.source()
    compile(generated, "<generated-recording>", "exec")
    assert "home()" in generated and "tap(" in generated
    session = managed / "recordings" / "workflow.json"
    dialogs.filename(session)
    click(window.recorder_panel, "Save session…")
    spin(application, lambda: session.exists())
    window.editor.set_text("")
    spin(application, lambda: js("window.studio.getText()") == "")
    click(window.recorder_panel, "Insert Python into Monaco")
    spin(application, lambda: "tap(" in window.editor.source and "home()" in window.editor.source)
    source = window.editor.source
    window.actions["save"].trigger()
    # Compare the actual UTF-8 bytes: read_text() translates Windows CRLF,
    # whereas Monaco legitimately returns its model's native line endings.
    assert script.read_bytes().decode("utf-8") == source
    checks["recorded_python"] = True

    # Persist a once-only schedule via TaskDialog and approve its exact snapshot.
    navigation(window, "tasks")
    def define(dialog):
        dialog.name.setText("Integrated once-only simulation")
        dialog.schedule.setCurrentText("once")
        dialog.at.setText((datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat())
        dialog.missed.setCurrentText("run_once")
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    dialogs.expect(TaskDialog, define)
    click(window.task_panel, "Create from editor…")
    spin(application, lambda: window.task_panel.tasks.rowCount() == 1)
    window.task_panel.tasks.selectRow(0)
    task = window.task_panel.selected()
    assert task is not None and task.project_root == str(managed)
    def approve(dialog):
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    dialogs.expect(QDialog, approve)
    click(window.task_panel, "Approve source…")
    assert window.scheduler.is_authorized(task)
    click(window.task_panel, "Resume scheduling")
    spin(application, lambda: bool(window.task_store.history(task.task_id)) and window.task_store.history(task.task_id)[0]["state"] == "completed")
    history = window.task_store.history(task.task_id)
    assert len(history) == 1 and history[0]["run_id"]
    assert any(run.run_id == history[0]["run_id"] and run.backend == "simulation" for run in window.run_states)
    assert window.simulations.client(serial).state()["screen"] == "dashboard"
    checks["scheduled_worker"] = True
    spin(application, lambda: window.task_panel.history.item(0, 0) is not None
         and window.task_panel.history.item(0, 0).text() == "completed")
    checks["durable_history"] = window.task_panel.history.rowCount() == 1
    if screenshots:
        QTest.qWait(100)
        window.grab().save(str(screenshots / "scheduled-history.png"))

    navigation(window, "projects")
    # Reopen explicitly if switching script tabs selected another project.
    if window.project_panel.store is None:
        dialogs.directory(managed)
        click(window.project_panel, "Open project…")
        spin(application, lambda: window.project_panel.store is not None and not window.project_panel.busy)
    exported = root / "preserved.zip"
    dialogs.filename(exported)
    click(window.project_panel, "Export ZIP…")
    spin(application, lambda: exported.exists() and not window.project_panel.busy)
    dialogs.filename(exported)
    dialogs.directory(root)
    dialogs.text("restored-workflow")
    click(window.project_panel, "Import / restore ZIP…")
    restored = root / "restored-workflow"
    spin(application, lambda: window.project_root == restored and not window.project_panel.busy)
    assert (restored / "scripts" / "main.py").read_bytes().decode("utf-8") == source
    assert (restored / "images" / "start.png").read_bytes() == (managed / "images" / "start.png").read_bytes()
    assert (restored / "recordings" / "workflow.json").exists()
    checks["archive_restore"] = True
    if screenshots:
        QTest.qWait(100)
        window.grab().save(str(screenshots / "projects-preserved.png"))
    assert not native_calls and not dialogs.actions and dialogs.error is None
    window.close()
    spin(application, lambda: window._shutdown_complete)

    # Restart creates a new runtime; persisted schedules/history stay unapproved.
    restarted = StudioWindow(discover=False)
    restarted.resize(1520, 1040)
    restarted.show()
    spin(application, lambda: restarted.editor.is_ready and not restarted.jobs)
    loaded = restarted.task_store.get(task.task_id)
    assert restarted.task_store.history(task.task_id)[0]["state"] == "completed"
    assert not restarted.scheduler.is_authorized(loaded) and restarted.scheduler.paused
    assert restarted.active_simulation is None and not restarted.run_states
    navigation(restarted, "projects")
    dialogs.directory(restored)
    click(restarted.project_panel, "Open project…")
    spin(application, lambda: restarted.project_root == restored and not restarted.project_panel.busy)
    assert ProjectStore.open(restored).metadata["name"] == "managed-workflow"
    checks["restart_revokes_trust"] = True
    restarted.close()
    spin(application, lambda: restarted._shutdown_complete)
    print(json.dumps(checks), flush=True)
    application.processEvents()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
