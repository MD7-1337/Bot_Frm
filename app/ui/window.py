from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time

from PySide6.QtCore import QObject, QRunnable, QSettings, QSignalBlocker, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QImage, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QDockWidget, QFileDialog, QLabel, QListWidget, QListWidgetItem,
                              QMainWindow, QMessageBox, QPlainTextEdit, QToolBar)

from app.automation.qt_service import RuntimeService
from app.devices.adb import AdbClient
from app.devices.paths import adb_executable
from app.devices.registry import DeviceRegistry
from app.editor.widget import EditorWidget
from app.projects.library import discover_project
from app.streaming.capture import CaptureService
from app.streaming.manager import StreamManager
from app.ui.capture_dialog import CaptureDialog
from app.ui.execution_panel import ExecutionPanel
from app.ui.live_panel import LivePanel
from app.ui.preview import PhonePreview


class JobSignals(QObject):
    done = Signal(object, object, object)


class Job(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = JobSignals()

    def run(self):
        try:
            self.signals.done.emit(self, self.operation(), None)
        except Exception as error:
            self.signals.done.emit(self, None, str(error))


class StudioWindow(QMainWindow):
    """Device/video/capture workbench; unrelated advanced phases remain unavailable."""

    def __init__(self, *, discover=True):
        super().__init__()
        self.setWindowTitle("Android Automation Studio · Script Studio")
        self.resize(1380, 880)
        self.settings = QSettings("AndroidAutomationStudio", "Phase0")
        self.adb = AdbClient(adb_executable())
        self.capture = CaptureService(self.adb)
        self.registry = DeviceRegistry()
        self.streams = StreamManager(self.adb)
        self._connection_tokens: dict[str, threading.Event] = {}
        self._observed_generations: dict[str, tuple[int, str]] = {}
        self._preview_modes: dict[str, str] = {}
        self._stream_sequences: dict[str, int] = {}
        self._stream_states: dict[str, str] = {}
        self._capture_dialogs: set[CaptureDialog] = set()
        self.runtime = RuntimeService(max_workers=4, parent=self)
        self.run_states = []
        self.pending_runs: dict[str, str] = {}
        self.pending_run_ids: dict[str, str] = {}
        self._emergency_latched = False
        self._manual_cancel = threading.Event()
        self._closing = False
        self._shutdown_complete = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.jobs: dict[Job, object] = {}
        self.pending_controls: set[str] = set()
        self.capture_pending = False
        self.discover_pending = False
        self.path: Path | None = None
        self.project_root = Path.cwd().resolve()
        self._project_explicit = False
        self.assignments: dict[str, Path] = {}
        self._request_documents: dict[str, dict] = {}
        self._run_documents: dict[str, dict] = {}
        self._run_lines: dict[str, tuple[str, int]] = {}
        self.saved_source = ""
        self.editor = EditorWidget()
        self.setCentralWidget(self.editor)
        self.project_label = QLabel(f"Project: {self.project_root}")
        self.project_label.setToolTip("Images resolve from this project's images directory and contained script paths.")
        self.statusBar().addPermanentWidget(self.project_label)
        self.devices = QListWidget()
        self.devices.setAccessibleName("Connected Android devices")
        self.devices.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.devices.currentItemChanged.connect(self._selection_changed)
        self.preview = PhonePreview()
        self.preview.gesture.connect(self._gesture)
        self.preview.double_tap.connect(lambda x, y: self._double_tap(self.selected_serial(), self.preview, x, y))
        self.preview.coordinate.connect(lambda x, y: self.statusBar().showMessage(f"Device coordinates: {x}, {y}"))
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(2000)
        self.logs.setAccessibleName("Diagnostic and execution log")
        self.runtime.event.connect(self._runtime_event)
        self.runtime.snapshot_changed.connect(self._runtime_snapshot)
        self.runtime.failure.connect(self.log)
        self._dock("Devices", "devices", self.devices, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.live_panel = LivePanel(self.preview)
        self.live_panel.start_requested.connect(self.start_live)
        self.live_panel.start_all_requested.connect(self.start_all_live)
        self.live_panel.stop_requested.connect(self.stop_live)
        self.live_panel.fallback_requested.connect(self.screenshot_fallback)
        self._dock("Phone previews · scrcpy / screenshot fallback", "phone", self.live_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self.execution_panel = ExecutionPanel(self.logs)
        self.execution_panel.run_selected.connect(lambda _: self._show_execution_line())
        self._dock("Scripts and output", "events", self.execution_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.editor.error.connect(self.log)
        self.editor.document_changed.connect(lambda _: self._update_title())
        self._build_actions()
        self.editor.set_project_root(self.project_root)
        self.editor.set_text('# Assigned phone: simple functions and device methods share one context.\nprint(getDevice())\n# click(Pattern("start.png").similar(0.9))\n')
        self.saved_source = self.editor.source
        self.default_state = self.saveState()
        geometry = self.settings.value("geometry")
        state = self.settings.value("layout")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.capture_selected)
        self.preview_timer.start(1000)
        self.stream_timer = QTimer(self)
        self.stream_timer.timeout.connect(self._update_live_frames)
        self.stream_timer.start(33)
        self.discovery_timer = QTimer(self)
        self.discovery_timer.timeout.connect(self.refresh_devices)
        if discover:
            self.discovery_timer.start(3000)
        self.log("Scripting engine: project image targets, isolated device contexts, cancellable waits and pause/resume.")
        self.log("Real-phone and Windows compatibility still require hardware validation. Debugger, OCR and scheduler are later phases.")
        if discover:
            QTimer.singleShot(0, self.refresh_devices)

    def _dock(self, title, name, widget, area):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def _action(self, menu, title, callback, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def _build_actions(self):
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "Open Python script…", self.open_script, QKeySequence.StandardKey.Open)
        self._action(file_menu, "Save script", self.save_script, QKeySequence.StandardKey.Save)
        self._action(file_menu, "Save script as…", lambda: self.save_script(save_as=True), QKeySequence.StandardKey.SaveAs)
        self._action(file_menu, "Choose project image library…", self.choose_project)
        toolbar = QToolBar("Device and execution actions", self)
        toolbar.setObjectName("mainToolbar")
        self.addToolBar(toolbar)
        self._action(toolbar, "Refresh devices", self.refresh_devices)
        self._action(toolbar, "Capture PNG…", self.save_capture)
        self._action(toolbar, "Capture image region…", self.capture_region, "Ctrl+Shift+C")
        self._action(toolbar, "Home", lambda: self._key("HOME"))
        self._action(toolbar, "Back", lambda: self._key("BACK"))
        self.run_action = self._action(toolbar, "Run trusted script…", self.run_script, "F5")
        self._action(toolbar, "Pause run", lambda: self._control_run("pause"), "F6")
        self._action(toolbar, "Resume run", lambda: self._control_run("resume"), "Shift+F6")
        self._action(toolbar, "Stop run", lambda: self._control_run("cancel"), "Shift+F5")
        self._action(toolbar, "Emergency stop", self.emergency_stop, "Ctrl+Shift+F12")
        self.reset_stop_action = self._action(toolbar, "Reset emergency stop", self.reset_emergency_stop)
        self.reset_stop_action.setEnabled(False)
        insert_menu = self.menuBar().addMenu("Insert API")
        for label, code in (("Image click", 'click("target.png")\n'),
                            ("Double click", 'doubleClick("target.png")\n'),
                            ("Long press", 'longPress("target.png", duration=2)\n'),
                            ("Tap", "tap(100, 200)\n"),
                            ("Swipe", "swipe(200, 600, 200, 200, duration=0.5)\n"),
                            ("Drag", "drag(200, 600, 200, 200, duration=1)\n"),
                            ("Scroll", 'scroll("down", amount=1)\n'),
                            ("Find", 'match = find("target.png")\n'),
                            ("Find all", 'matches = findAll("target.png")\n'),
                            ("Exists condition", 'if exists("target.png"):\n    click("target.png")\n'),
                            ("Wait for image", 'waitImage("target.png", timeout=10)\n'),
                            ("Wait to vanish", 'waitVanish("loading.png", timeout=15)\n'),
                            ("Pattern with region", 'target = Pattern("target.png").similar(0.9).inRegion(Region(0, 0, 100, 100))\n'),
                            ("Delay", "sleep(1)\n"), ("Home", "home()\n"), ("Back", "back()\n"),
                            ("Launch app", 'launchApp("com.example.app")\n'),
                            ("Stop app", 'stopApp("com.example.app")\n'),
                            ("Type text", 'typeText("hello")\n'),
                            ("Capture", "screen = capture()\n"),
                            ("Explicit device", 'device.waitImage("target.png", timeout=10)\n')):
            self._action(insert_menu, label, lambda checked=False, text=code: self.editor.insert(text))
        api_toolbar = QToolBar("SikuliX commands", self)
        api_toolbar.setObjectName("automationToolbar")
        self.addToolBarBreak()
        self.addToolBar(api_toolbar)
        for label, code in (("Click image", 'click("target.png")\n'),
                            ("Find image", 'match = find("target.png")\n'),
                            ("Wait image", 'wait("target.png", timeout=10)\n'),
                            ("Delay", "wait(2)\n"),
                            ("Loop", "for attempt in range(3):\n    sleep(1)\n")):
            self._action(api_toolbar, label, lambda checked=False, text=code: self.editor.insert(text))
        execution_menu = self.menuBar().addMenu("Execution")
        self._action(execution_menu, "Run editor on selected phones…", self.run_selected_scripts, "Ctrl+F5")
        self._action(execution_menu, "Assign Python file to current phone…", self.assign_script)
        self._action(execution_menu, "Run assigned files on selected phones…", self.run_assigned_scripts)
        view_menu = self.menuBar().addMenu("&View")
        for dock in self.findChildren(QDockWidget):
            view_menu.addAction(dock.toggleViewAction())
        self._action(view_menu, "Reset layout", lambda: self.restoreState(self.default_state))
        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "Scripting capabilities", lambda: QMessageBox.information(
            self, "Development status", "This is a development build, not a production release.\n\n"
            "Available: image-based Python API, project image library, Monaco signatures/hover previews, isolated runs, pause/resume/stop, ADB and scrcpy previews.\n\n"
            "Real-phone and Windows acceptance is outstanding. General Python language service, OCR, recording, debugger, scheduling and release packages remain unavailable. See docs/SCRIPTING_API.md."))

    def log(self, message):
        self.logs.appendPlainText(time.strftime("%H:%M:%S ") + str(message))

    def _submit(self, operation, callback):
        job = Job(operation)
        self.jobs[job] = callback
        # An explicit QObject slot/queued connection gives completion callbacks
        # the window's GUI thread, independent of Python closure affinity.
        job.signals.done.connect(self._job_done, Qt.ConnectionType.QueuedConnection)
        self.pool.start(job)

    @Slot(object, object, object)
    def _job_done(self, job, result, error):
        callback = self.jobs.pop(job, None)
        if callback is not None and not self._closing:
            callback(result, error)

    def selected_serial(self):
        item = self.devices.currentItem()
        if item:
            device = item.data(Qt.ItemDataRole.UserRole)
            return device.serial if device.available else None
        return None

    def busy(self, serial):
        return (serial in self.pending_controls or serial in self.pending_runs.values()
                or any(r.serial == serial and r.exitcode is None for r in self.run_states))

    def refresh_devices(self):
        if self.discover_pending or self._closing:
            return
        self.discover_pending = True
        selected = self._selected_identity()
        def finished(devices, error):
            self.discover_pending = False
            if error:
                self.log(error)
                observed = self.registry.mark_unknown()
            else:
                observed = self.registry.update(devices)
            self._apply_device_states(observed)
            blocker = QSignalBlocker(self.devices)
            self.devices.clear()
            selected_item = None
            for device in observed:
                item = QListWidgetItem(f"{device.model or device.serial}\n{device.serial} · {device.state}")
                item.setData(Qt.ItemDataRole.UserRole, device)
                self.devices.addItem(item)
                if device.serial == selected:
                    selected_item = item
            if selected_item:
                self.devices.setCurrentItem(selected_item)
            elif self.devices.count():
                # Prefer available devices only on initial selection, never
                # redirect an existing phone's controls after disconnection.
                candidates = [i for i in range(self.devices.count()) if self.devices.item(i).data(Qt.ItemDataRole.UserRole).available]
                self.devices.setCurrentRow(candidates[0] if candidates else 0)
            del blocker
            if not observed:
                self.log("No devices reported by ADB. Connect a phone and authorize USB debugging.")
            if selected != self._selected_identity():
                self._selection_changed(self.devices.currentItem(), None)
        self._submit(self.adb.devices, finished)

    def _connection_token(self, serial):
        return self._connection_tokens.setdefault(serial, threading.Event())

    def _selected_identity(self):
        item = self.devices.currentItem()
        return item.data(Qt.ItemDataRole.UserRole).serial if item else None

    def _apply_device_states(self, devices):
        for device in devices:
            signature = (device.generation, device.state)
            if self._observed_generations.get(device.serial) == signature:
                continue
            self._observed_generations[device.serial] = signature
            if not device.available:
                self._connection_token(device.serial).set()
                self.runtime.invalidate_device(device.serial)
                self.streams.stop(device.serial)
                self.capture.forget(device.serial)
                if self.preview.frame and self.preview.frame.serial == device.serial:
                    self.preview.clear()
                if device.serial in self.live_panel.tiles:
                    self.live_panel.tiles[device.serial][1].clear()
                self.live_panel.update_status(device.serial, device.state, self.selected_serial())
            elif self._connection_token(device.serial).is_set():
                self._connection_tokens[device.serial] = threading.Event()
                # Explicit user restart is required; no script/input replay.
                self._preview_modes[device.serial] = "stopped"

    def _device_available(self, serial):
        device = self.registry.get(serial) if serial else None
        return bool(device and device.available)

    def _selection_changed(self, current, previous):
        self.preview.clear()
        self._show_execution_line()
        serial = self.selected_serial()
        self.live_panel.status.setText(f"{serial or 'No available device'} · {self._preview_modes.get(serial, 'ADB screenshot fallback')}")
        self.live_panel.geometry_label.setText("Resolution / orientation: awaiting current device frame")
        if serial and self._device_available(serial):
            token = self._connection_token(serial)
            def metadata(info, error):
                if token.is_set() or serial != self.selected_serial():
                    return
                if error:
                    self.log(error)
                else:
                    orientation = f"{info.orientation}°" if info.orientation is not None else "unavailable"
                    self.live_panel.geometry_label.setText(f"Android {info.width} × {info.height} · rotation {orientation}")
            self._submit(lambda: self.adb.screen_info(serial), metadata)
        self.capture_selected()

    def capture_selected(self):
        serial = self.selected_serial()
        if (not serial or self.capture_pending or self.busy(serial) or self._closing
                or self._preview_modes.get(serial, "screenshot") != "screenshot"):
            return
        token = self._connection_token(serial)
        self.capture_pending = True
        def finished(frame, error):
            self.capture_pending = False
            if token.is_set() or serial != self.selected_serial() or self._preview_modes.get(serial, "screenshot") != "screenshot":
                return
            if error:
                self.preview.clear()
                self.log(error)
            else:
                try:
                    self.preview.set_frame(frame)
                    self.live_panel.status.setText(f"{serial} · ADB screenshot fallback (not video)")
                except ValueError as exception:
                    self.preview.clear()
                    self.log(str(exception))
        self._submit(lambda: self.capture.capture(serial), finished)

    def _control(self, serial, operation):
        if self._emergency_latched:
            self.log("Emergency stop is latched. Reset it before sending device input.")
            return
        if not serial or not self._device_available(serial) or self.busy(serial) or self._closing:
            self.log("Select an available, idle phone. Manual control is blocked while its worker runs.")
            return
        self.pending_controls.add(serial)
        cancelled = self._manual_cancel
        connection = self._connection_token(serial)
        generation = self.registry.get(serial).generation
        def dispatch():
            current = self.registry.get(serial)
            if cancelled.is_set() or connection.is_set() or not current or not current.available or current.generation != generation:
                raise RuntimeError("Control command cancelled by emergency stop or changed device connection")
            return operation()
        def finished(result, error):
            self.pending_controls.discard(serial)
            self.log(error or f"Control command completed on {serial}")
        self._submit(dispatch, finished)

    def _key(self, key):
        serial = self.selected_serial()
        self._control(serial, lambda: self.adb.key(serial, key))

    def _gesture(self, start, end, milliseconds):
        serial = self.selected_serial()
        self._gesture_on(serial, self.preview, start, end, milliseconds)

    def _gesture_on(self, serial, preview, start, end, milliseconds):
        frame = preview.frame
        if not frame or frame.serial != serial or time.monotonic() - frame.captured_at > 3:
            self.log("Preview is stale. Capture a fresh frame before sending input.")
            return
        if start == end and milliseconds < 500:
            self._control(serial, lambda: self.adb.tap(serial, *start))
        else:
            self._control(serial, lambda: self.adb.swipe(serial, *start, *end, duration_ms=milliseconds))

    def _double_tap(self, serial, preview, x, y):
        frame = preview.frame
        if not frame or frame.serial != serial or time.monotonic() - frame.captured_at > 3:
            self.log("Preview is stale. Wait for a fresh frame before double tapping.")
            return
        cancelled = self._manual_cancel
        connection = self._connection_token(serial)
        def operation():
            self.adb.tap(serial, x, y)
            if cancelled.wait(0.12) or connection.is_set() or not self._device_available(serial):
                raise RuntimeError("Second tap cancelled")
            self.adb.tap(serial, x, y)
        self._control(serial, operation)

    def start_live(self, checked=False, *, serial=None):
        serial = serial or self.selected_serial()
        if self._closing or not self._device_available(serial):
            self.log("Select an authorized connected phone to start video.")
            return
        try:
            self.streams.start(serial, self.live_panel.options())
            self._preview_modes[serial] = "live"
            self._stream_sequences.pop(serial, None)
            view = self.live_panel.tile(serial)
            if not view.property("controlsConnected"):
                view.gesture.connect(lambda start, end, ms, device=serial, widget=view: self._gesture_on(device, widget, start, end, ms))
                view.double_tap.connect(lambda x, y, device=serial, widget=view: self._double_tap(device, widget, x, y))
                view.coordinate.connect(lambda x, y, device=serial: self.statusBar().showMessage(f"{device} · Android {x}, {y}"))
                view.setProperty("controlsConnected", True)
            view.clear()
            if serial == self.selected_serial():
                self.preview.clear()
        except Exception as error:
            self.log(str(error))

    def start_all_live(self):
        for device in self.registry.snapshot():
            if device.available:
                self.start_live(serial=device.serial)

    def stop_live(self):
        serial = self._selected_identity()
        if serial:
            self.streams.stop(serial)
            self._preview_modes[serial] = "stopped"
            self.preview.clear()
            if serial in self.live_panel.tiles:
                self.live_panel.tiles[serial][1].clear()
            self.live_panel.status.setText(f"{serial} · stopped; choose Start live or Screenshot fallback")

    def screenshot_fallback(self):
        serial = self.selected_serial()
        if not serial:
            self.log("Select an authorized phone first.")
            return
        self.stop_live()
        self._preview_modes[serial] = "screenshot"
        self.capture_selected()

    def _update_live_frames(self):
        if self._closing:
            return
        selected = self.selected_serial()
        for serial, state in self.streams.statuses().items():
            text = f"scrcpy 3.1 · {state.state}"
            if state.error:
                text += f" · {state.error}"
            self.live_panel.update_status(serial, text, selected)
            if self._stream_states.get(serial) != text:
                self.log(f"{serial}: {text}")
                self._stream_states[serial] = text
                if state.state in ("failed", "stopped") and self._preview_modes.get(serial) == "live":
                    if serial in self.live_panel.tiles:
                        self.live_panel.tiles[serial][1].clear()
                    if serial == selected:
                        self.preview.clear()
            frame = self.streams.latest(serial)
            if frame is None or not self._device_available(serial) or self._preview_modes.get(serial) != "live":
                continue
            tile = self.live_panel.tile(serial)
            if self._stream_sequences.get(serial) != frame.sequence:
                try:
                    tile.set_video_frame(frame)
                    self._stream_sequences[serial] = frame.sequence
                except ValueError as error:
                    self.streams.stop(serial)
                    self.log(str(error))
                    continue
            if serial == selected and self.preview.frame is not frame:
                try:
                    self.preview.set_video_frame(frame)
                    self.live_panel.geometry_label.setText(
                        f"Android {frame.source_width} × {frame.source_height} · encoded {frame.width} × {frame.height}"
                        f" · rotation {str(frame.orientation) + '°' if frame.orientation is not None else 'unavailable'}")
                except ValueError as error:
                    self.streams.stop(serial)
                    self.preview.clear()
                    self.log(str(error))

    def capture_region(self):
        serial = self.selected_serial()
        if not serial or self._closing:
            self.log("Select an authorized phone before capturing an image region.")
            return
        token = self._connection_token(serial)
        script = self.path
        def current_image():
            if token.is_set() or not self._device_available(serial):
                raise RuntimeError("Device connection changed. Reconnect and capture again.")
            captured = self.capture.capture(serial)
            if token.is_set():
                raise RuntimeError("Device disconnected during capture")
            image = QImage.fromData(captured.png, "PNG")
            if image.isNull():
                raise ValueError("Device screenshot could not be decoded")
            return image

        def open_dialog(image, error):
            if token.is_set():
                return
            if error:
                self.log(error)
                return
            try:
                image_root = self.project_root / "images"
                image_root.mkdir(exist_ok=True)
            except OSError as exception:
                self.log(str(exception))
                return
            dialog = CaptureDialog(image, serial, parent=self, test_frame_provider=current_image,
                                   script_directory=script.parent if script else None,
                                   save_directory=image_root)
            self._capture_dialogs.add(dialog)
            dialog.reference_ready.connect(lambda code: self._insert_asset_reference(code, script))
            dialog.asset_saved.connect(lambda path, region: self.log(f"Saved {path} · Android {region}"))
            def finished(result):
                self._capture_dialogs.discard(dialog)
                dialog.deleteLater()
            dialog.finished.connect(finished)
            dialog.show()
        # A full-resolution ADB freeze avoids saving scaled video templates;
        # live rendering continues independently while selection is open.
        self._submit(current_image, open_dialog)

    def _insert_asset_reference(self, code, script):
        if self.path != script or not self.editor.is_ready:
            self.log(f"Image saved; editor document changed. Reference: {code.strip()}")
            return
        import ast
        from app.projects.library import AssetLibrary
        try:
            assignment = ast.parse(code).body[0]
            reference = ast.literal_eval(assignment.value)
            AssetLibrary(self.project_root, self.path.parent if self.path else None).resolve(reference)
        except (OSError, ValueError, SyntaxError, AttributeError, IndexError) as error:
            self.log(f"Image saved, but its reference is outside or unavailable in this project: {error}")
            return
        self.editor.insert(code + "click(image_path)\n")

    def _set_project(self, root, *, explicit=True):
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Choose an existing project directory")
        script_dir = self.path.parent if self.path and self.path.is_relative_to(root) else None
        self.editor.set_project_root(root, script_dir=script_dir)
        self.project_root = root
        self._project_explicit = explicit
        self.project_label.setText(f"Project: {root}")
        self.log(f"Image library: {root / 'images'} · project: {root}")

    def choose_project(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose project image library root", str(self.project_root))
        if directory:
            try:
                self._set_project(directory)
            except (OSError, ValueError) as error:
                self.log(str(error))

    def save_capture(self):
        frame = self.preview.frame
        if frame is None:
            self.log("Capture requires a current device frame.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save device screenshot", "capture.png", "PNG (*.png)")
        if path:
            try:
                if hasattr(frame, "png"):
                    self._atomic_write(Path(path), frame.png)
                else:
                    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
                    encoded = QByteArray()
                    buffer = QBuffer(encoded)
                    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not self.preview.image.save(buffer, "PNG"):
                        raise OSError("Could not encode the selected video frame as PNG")
                    self._atomic_write(Path(path), bytes(encoded))
                self.log(f"Saved screenshot: {path}")
            except OSError as error:
                self.log(str(error))

    def _confirm_discard(self):
        if self.editor.source == self.saved_source:
            return True
        answer = QMessageBox.question(self, "Unsaved changes", "Save changes to the current script?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return self.save_script() if answer == QMessageBox.StandardButton.Save else answer == QMessageBox.StandardButton.Discard

    def open_script(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Python script", "", "Python (*.py)")
        if path:
            try:
                candidate = Path(path)
                if candidate.stat().st_size > 1_000_000:
                    raise ValueError("Script exceeds 1 MB limit")
                source = candidate.read_text(encoding="utf-8")
                self.editor.set_text(source)
                self.path = candidate
                self.saved_source = source
                if self._project_explicit and candidate.resolve().is_relative_to(self.project_root):
                    self._set_project(self.project_root)
                else:
                    self._set_project(discover_project(candidate), explicit=False)
                self._update_title()
            except (OSError, ValueError) as error:
                self.log(str(error))

    @staticmethod
    def _atomic_write(path, data):
        from PySide6.QtCore import QIODevice, QSaveFile
        output = QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        if output.write(data) != len(data) or not output.commit():
            output.cancelWriting()
            raise OSError(output.errorString())

    def save_script(self, checked=False, *, save_as=False):
        path = self.path
        if path is None or save_as:
            name, _ = QFileDialog.getSaveFileName(self, "Save Python script", str(path or "script.py"), "Python (*.py)")
            if not name:
                return False
            path = Path(name)
        try:
            self._atomic_write(path, self.editor.source.encode("utf-8"))
            self.path = path
            self.saved_source = self.editor.source
            if not path.resolve().is_relative_to(self.project_root):
                self._set_project(discover_project(path), explicit=False)
            else:
                self.editor.set_project_root(self.project_root, script_dir=path.resolve().parent)
            self._update_title()
            return True
        except (OSError, ValueError) as error:
            self.log(str(error))
            return False

    def _update_title(self):
        dirty = " *" if self.editor.source != self.saved_source else ""
        self.setWindowTitle(f"{self.path.name if self.path else 'Untitled.py'}{dirty} · Android Automation Studio · Script Studio")
        self._show_execution_line()

    def run_script(self):
        serial = self.selected_serial()
        self._approve_and_run([(serial, self.editor.source, str(self.path or "<editor>"), self.project_root)])

    def _selected_phones(self):
        return [item.data(Qt.ItemDataRole.UserRole).serial for item in self.devices.selectedItems()
                if item.data(Qt.ItemDataRole.UserRole).available]

    def run_selected_scripts(self):
        phones = self._selected_phones()
        self._approve_and_run([(serial, self.editor.source, str(self.path or "<editor>"), self.project_root)
                               for serial in phones])

    def assign_script(self):
        serial = self.selected_serial()
        if not serial:
            self.log("Select an authorized phone before assigning a script.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, f"Assign Python file to {serial}", str(self.project_root), "Python (*.py)")
        if filename:
            path = Path(filename).resolve()
            self.assignments[serial] = path
            self.log(f"Assigned {path} to {serial}. Running still requires explicit trust approval.")
            self.devices.currentItem().setToolTip(f"Assigned script: {path}")

    def run_assigned_scripts(self):
        requests = []
        try:
            for serial in self._selected_phones():
                path = self.assignments.get(serial)
                if path is None:
                    raise ValueError(f"Assign a Python file to {serial} first")
                if path.stat().st_size > 1_000_000:
                    raise ValueError(f"Script exceeds size limit: {path}")
                root = self.project_root if path.is_relative_to(self.project_root) else discover_project(path)
                requests.append((serial, path.read_text(encoding="utf-8"), str(path), root))
        except (OSError, ValueError) as error:
            self.log(str(error))
            return
        self._approve_and_run(requests)

    def _approve_and_run(self, requests):
        if not self.editor.is_ready or not requests or self._closing or self._emergency_latched:
            self.log("Wait for the editor and select available phones; reset emergency stop before running.")
            return
        try:
            for serial, source, script_id, root in requests:
                if not serial or not self._device_available(serial) or self.busy(serial):
                    raise ValueError(f"Select an idle authorized phone: {serial or 'none'}")
                if script_id != "<editor>" and not Path(script_id).resolve().is_relative_to(Path(root).resolve()):
                    raise ValueError("Open or save the script inside the active project before running")
                compile(source, script_id, "exec")
        except (ValueError, SyntaxError) as error:
            self.log(str(error))
            return
        listing = "\n".join(f"{serial}: {script_id}" for serial, _, script_id, _ in requests)
        approved = QMessageBox.warning(self, "Approve trusted Python execution",
            f"Run these source snapshots?\n{listing}\n\nPython has your Windows/user permissions and can access files, networks and other devices. Worker isolation is not a security sandbox. Run only code you trust.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if approved != QMessageBox.StandardButton.Yes:
            return
        for serial, source, script_id, root in requests:
            try:
                # The modal trust dialog processes Qt timers. Revalidate each
                # phone, but execute exactly the source snapshot that was approved.
                if self.busy(serial) or not self._device_available(serial) or self._closing or self._emergency_latched:
                    raise RuntimeError(f"Phone {serial} became unavailable or busy; no run queued")
                self.runtime.allow_device(serial)
                if self.preview.frame and self.preview.frame.serial == serial:
                    self.preview.cancel_input()
                if serial in self.live_panel.tiles:
                    self.live_panel.tiles[serial][1].cancel_input()
                request_id = self.runtime.start(source, serial, trusted=True, backend="adb",
                    adb_executable=self.adb.executable, script_id=script_id, project_root=str(root))
                self.pending_runs[request_id] = serial
                self._request_documents[request_id] = {"source": source, "script_id": script_id, "project_root": str(root)}
                self.log(f"Queued run request {request_id} on {serial}")
            except Exception as error:
                self.log(str(error))

    def _active_run_id(self):
        selected = self.execution_panel.selected_run()
        if selected:
            return selected
        serial = self.selected_serial()
        return next((run.run_id for run in reversed(self.run_states)
                     if run.serial == serial and run.exitcode is None), None)

    def _control_run(self, operation):
        run_id = self._active_run_id()
        if not run_id:
            self.log("Select an active script run or its phone first.")
            return
        try:
            getattr(self.runtime, operation)(run_id)
            self.log(f"{operation.capitalize()} requested for {run_id}; waiting for worker acknowledgment.")
        except Exception as error:
            self.log(str(error))

    def _show_execution_line(self):
        if not hasattr(self, "execution_panel"):
            return
        run_id = self._active_run_id()
        document = self._run_documents.get(run_id)
        location = self._run_lines.get(run_id)
        run = next((item for item in self.run_states if item.run_id == run_id), None)
        state = run.state if run else "idle"
        self.editor.set_run_status(state)
        expected_path = str(self.path or "<editor>")
        if (document and location and document["source"] == self.editor.source
                and document["script_id"] == expected_path and location[0] == expected_path
                and run and run.exitcode is None):
            self.editor.set_execution_line(location[1])
        else:
            self.editor.set_execution_line(None)

    def _runtime_event(self, event):
        self.execution_panel.on_event(event)
        if event.get("event") == "line":
            self._run_lines[event["run_id"]] = (event["source_path"], event["line"])
            self._show_execution_line()
            return
        if event.get("event") == "request_error":
            self.pending_runs.pop(event.get("request_id"), None)
            self.pending_run_ids.pop(event.get("request_id"), None)
            self._request_documents.pop(event.get("request_id"), None)
        if event.get("event") == "request" and event.get("command") == "start":
            request_id = event.get("request_id")
            if request_id in self.pending_runs:
                self.pending_run_ids[request_id] = event["run_id"]
                document = self._request_documents.pop(request_id, None)
                if document:
                    self._run_documents[event["run_id"]] = document
                self._release_confirmed_runs()
        if event.get("event") == "emergency_stopped":
            self.reset_stop_action.setEnabled(True)
        if event.get("event") == "request" and event.get("command") == "reset_emergency_stop":
            self._emergency_latched = False
            self._manual_cancel = threading.Event()
            self.run_action.setEnabled(True)
            self.reset_stop_action.setEnabled(False)
        if event.get("event") == "output":
            self.log(f"[{event.get('serial')} / {Path(event.get('script_id', '')).name}] {event.get('text', '').rstrip()}")
        elif event.get("event") == "error":
            self.log(f"[{event.get('serial')}] {event.get('error_type')}: {event.get('message')}\n{event.get('traceback', '')}")
        else:
            self.log(json.dumps(event, ensure_ascii=False))

    def _runtime_snapshot(self, states):
        self.run_states = list(states)
        self.execution_panel.update_runs(self.run_states)
        self._release_confirmed_runs()
        self._show_execution_line()

    def _release_confirmed_runs(self):
        # A previous completed run on the same serial does not acknowledge a
        # new request. Transfer the lease only to the exact acknowledged run.
        confirmed = {(state.run_id, state.serial) for state in self.run_states}
        for request_id, serial in list(self.pending_runs.items()):
            if (self.pending_run_ids.get(request_id), serial) in confirmed:
                self.pending_runs.pop(request_id)
                self.pending_run_ids.pop(request_id, None)

    def emergency_stop(self):
        self._emergency_latched = True
        self._manual_cancel.set()
        self.preview.cancel_input()
        for _, preview, _ in self.live_panel.tiles.values():
            preview.cancel_input()
        self.run_action.setEnabled(False)
        self.runtime.emergency_stop()
        self.log("Stop requested. An Android command already sent cannot be reversed.")

    def reset_emergency_stop(self):
        try:
            self.runtime.reset_emergency_stop()
        except RuntimeError as error:
            self.log(str(error))

    def closeEvent(self, event: QCloseEvent):
        if self._shutdown_complete:
            event.accept()
            return
        if not self._closing and not self._confirm_discard():
            event.ignore()
            return
        self._closing = True
        self._manual_cancel.set()
        self.run_action.setEnabled(False)
        self.preview_timer.stop()
        self.stream_timer.stop()
        self.discovery_timer.stop()
        for dialog in tuple(self._capture_dialogs):
            dialog.reject()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("layout", self.saveState())
        self.settings.sync()
        runtime_closed = self.runtime.close(timeout=0)
        streams_closed = self.streams.close(timeout=0)
        if not runtime_closed or not streams_closed or not self.pool.waitForDone(0) or self._capture_dialogs:
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        self.editor.shutdown()
        self._shutdown_complete = True
        event.accept()
