from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time

from PySide6.QtCore import QIODevice, QSaveFile, QStandardPaths, QObject, QRunnable, QSignalBlocker, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QImage, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QDockWidget, QFileDialog, QLabel, QListWidget, QListWidgetItem,
                              QApplication, QDialog, QInputDialog, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QToolBar, QVBoxLayout, QWidget)

from app.automation.qt_service import RuntimeService
from app.automation.recording import ActionRecorder, ScreenshotEvidence, MAX_SESSION_BYTES
from app.devices.adb import AdbClient, ScreenInfo, validate_endpoint
from app.devices.paths import adb_executable
from app.devices.registry import DeviceRegistry
from app.devices.diagnostics import ConnectionDiagnostics, SOLUTIONS
from app.editor.widget import EditorWidget
from app.projects.library import discover_project
from app.streaming.capture import CaptureService
from app.streaming.manager import StreamManager
from app.ui.capture_dialog import CaptureDialog
from app.ui.coordinate_inspector import CoordinateInspector
from app.ui.execution_panel import ExecutionPanel
from app.ui.live_panel import LivePanel
from app.ui.preview import PhonePreview
from app.ui.device_manager import DeviceManagerPanel, connection_overview
from app.ui.recorder_panel import RecorderPanel
from app.ui.visual_tools import VisualToolsPanel, load_asset, scan_assets
from app.ui.design import apply_theme, icon
from app.ui.shell import WorkspaceShell
from app.settings import create_store, integer, theme_name
from app.support import bug_report, event_logger
from app.host_metrics import HostMetrics
from app.simulation.model import SimulationManager, is_simulation, LABEL as SIMULATION_LABEL
from app.simulation.transport import SimulationTransport
from app.simulation.project import create_project as create_demo_project
from app.ui.simulation_panel import SimulationPanel
from app.ui.recognition_inspector import RecognitionInspector
from app.vision.ocr import TesseractOCR


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


class UnavailableScheduler:
    """Disabled lifecycle hooks when the preserved task database cannot open."""
    paused = True

    def tick(self):
        return None

    def handle_event(self, event):
        return None

    def set_busy_serials(self, states):
        return None

    def pause(self):
        return None

    emergency_stop = pause

    def revoke_device(self, serial):
        return None


class StudioWindow(QMainWindow):
    """Workspace controller; transport, decoding and trusted scripts run outside Qt callbacks."""
    diagnostic_progress = Signal(object)

    def __init__(self, *, discover=True):
        super().__init__()
        self.setWindowTitle("Android Automation Studio · Script Studio")
        self.resize(1380, 880)
        self.settings = create_store()
        data_root = Path(os.environ.get("STUDIO_DATA_DIR") or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "AndroidAutomationStudio")
        try:
            self.event_log, self.event_log_path = event_logger(data_root)
            self.event_log.info("Application startup; frozen=%s", bool(getattr(sys, 'frozen', False)))
        except OSError:
            self.event_log, self.event_log_path = None, None
        apply_theme(QApplication.instance(), theme_name(self.settings))
        self.adb = AdbClient(adb_executable(self.settings.value("adb_path", "")))
        self.capture = CaptureService(self.adb)
        self.registry = DeviceRegistry()
        self.simulations = SimulationManager()
        self.active_simulation = None
        self._simulation_pending = set()
        self._demo_projects = {}
        self._demo_pending = False
        self.streams = StreamManager(self.adb)
        if configured_server := os.environ.get("STUDIO_SCRCPY_SERVER") or self.settings.value("scrcpy_server_path", ""):
            self.streams.server_path = Path(configured_server).expanduser()
        self._connection_tokens: dict[str, threading.Event] = {}
        self._observed_generations: dict[str, tuple[int, str]] = {}
        self._preview_modes: dict[str, str] = {}
        self._stream_sequences: dict[str, int] = {}
        self._stream_states: dict[str, str] = {}
        self._capture_dialogs: set[CaptureDialog] = set()
        self.runtime = RuntimeService(max_workers=integer(self.settings, "worker_limit", 4, 1, 8), parent=self)
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
        self._screen_info = {}
        self._android_versions = {}
        self._network_pending = False
        self._connection_confirmation = None
        self._connection_problem = None
        self._diagnostic_busy = False
        self._diagnostic_serial = None
        self._diagnostic_cancel = threading.Event()
        self._discovery_message = None
        self._discovery_log_state = None
        self._last_discovery_error = None
        self._discovery_checked = False
        self._library_request = 0
        self._thumbnail_request = 0
        self.recorder = ActionRecorder()
        self.docks = {}
        self._request_documents: dict[str, dict] = {}
        self._run_documents: dict[str, dict] = {}
        self._run_lines: dict[str, tuple[str, int]] = {}
        self._task_connections = {}
        self.saved_source = ""
        self.editor = EditorWidget()
        self.project_label = QLabel(f"Project: {self.project_root}")
        self.project_label.setToolTip("Images resolve from this project's images directory and contained script paths.")
        self.devices = QListWidget()
        self.devices.setAccessibleName("Connected Android devices")
        self.devices.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.devices.currentItemChanged.connect(self._selection_changed)
        self.devices.itemClicked.connect(lambda item: self.select_real_device(item.data(Qt.ItemDataRole.UserRole).serial) if self.active_simulation else None)
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
        self.device_manager = DeviceManagerPanel(self.devices, self.settings)
        self.simulation_panel = SimulationPanel()
        self.device_manager.tabs.addTab(self.simulation_panel, "Simulation")
        self.simulation_panel.start_requested.connect(self.start_demo)
        self.simulation_panel.reset_requested.connect(self.reset_demo)
        self.simulation_panel.stop_requested.connect(self.stop_demo)
        self.simulation_panel.example_requested.connect(self.open_demo_example)
        self.device_manager.refresh_requested.connect(self.refresh_devices)
        self.device_manager.bug_report_requested.connect(self.export_bug_report)
        self.device_manager.compare_adb_requested.connect(self.compare_external_adb)
        self.device_manager.preview_requested.connect(self.open_preview)
        self.device_manager.capture_requested.connect(self.capture_region)
        self.device_manager.run_requested.connect(self.run_selected_scripts)
        self.device_manager.connect_requested.connect(lambda endpoint: self._network_action("connect", endpoint))
        self.device_manager.pair_requested.connect(self.pair_device)
        self.device_manager.disconnect_requested.connect(self.disconnect_device)
        self.device_manager.reconnect_requested.connect(self.reconnect_device)
        self.device_manager.diagnose_requested.connect(self.diagnose_connection)
        self.device_manager.cancel_diagnostics_requested.connect(lambda: self._diagnostic_cancel.set())
        self.diagnostic_progress.connect(self.device_manager.diagnostic_step)
        self._dock("Device Manager", "devices", self.device_manager, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.visual_tools = VisualToolsPanel()
        self.visual_tools.refresh_requested.connect(self.refresh_assets)
        self.visual_tools.capture_requested.connect(self.capture_region)
        self.visual_tools.save_requested.connect(self.save_capture)
        self.visual_tools.project_requested.connect(self.choose_project)
        self.visual_tools.asset_selected.connect(self.preview_asset)
        self.visual_tools.insert_requested.connect(self.insert_visual_command)
        self.visual_tools.test_requested.connect(self.test_asset)
        self.visual_tools.inspect_requested.connect(self.inspect_recognition)
        self._dock("Screenshot & Visual Tools", "visual", self.visual_tools, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.live_panel = LivePanel(self.preview)
        self.live_panel.start_requested.connect(self.start_live)
        self.live_panel.start_all_requested.connect(self.start_all_live)
        self.live_panel.stop_requested.connect(self.stop_live)
        self.live_panel.fallback_requested.connect(self.screenshot_fallback)
        self.live_panel.home_requested.connect(lambda: self._key("HOME"))
        self.live_panel.back_requested.connect(lambda: self._key("BACK"))
        self.live_panel.capture_requested.connect(self.capture_region)
        self._dock("Phone previews · scrcpy / screenshot fallback", "phone", self.live_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self.execution_panel = ExecutionPanel(self.logs)
        self.execution_panel.run_selected.connect(lambda _: self._show_execution_line())
        self.execution_panel.failure_selected.connect(self.inspect_run_failure)
        self._dock("Scripts and output", "events", self.execution_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.recorder_panel = RecorderPanel(self.recorder)
        self.recorder_panel.start_requested.connect(self.start_recording)
        self.recorder_panel.pause_requested.connect(self.pause_recording)
        self.recorder_panel.stop_requested.connect(self.stop_recording)
        self.recorder_panel.insert_requested.connect(self.insert_recording)
        self.recorder_panel.save_requested.connect(self.save_recording)
        self.recorder_panel.load_requested.connect(self.load_recording)
        self.recorder_panel.replay_requested.connect(self.replay_recording)
        self.recorder_panel.convert_requested.connect(self.convert_recorded_tap)
        self._dock("Action Recorder", "recorder", self.recorder_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.editor.error.connect(self.log)
        self.editor.error.connect(lambda _: self.event_log.warning("Monaco editor error; see dependency health") if self.event_log else None)
        self.editor.document_changed.connect(lambda _: self._update_title())
        self._build_actions()
        from app.tasks.store import TaskStore
        from app.tasks.scheduler import TaskScheduler
        from app.ui.task_panel import TaskPanel
        from app.ui.project_panel import ProjectPanel
        from app.ui.debugger_panel import DebuggerPanel
        from app.automation.recovery_journal import RecoveryJournal
        from app.ui.recovery_panel import RecoveryPanel
        data_root = Path(os.environ.get("STUDIO_DATA_DIR") or
                         QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        try:
            self.recovery_journal = RecoveryJournal(data_root / "failures.sqlite3")
            self.recovery_panel = RecoveryPanel(self.recovery_journal)
        except Exception as error:
            self.recovery_journal = None
            self.recovery_panel = QLabel(f"Failure history unavailable: {error}\nThe database was preserved. Check storage/permissions or restore a backup.")
            self.recovery_panel.setWordWrap(True)
        try:
            self.task_store = TaskStore(data_root / "tasks.sqlite3")
            self.scheduler = TaskScheduler(self.task_store, self._dispatch_task, self.runtime.cancel,
                lambda serial: self._device_available(serial) and not self.busy(serial) and not self._closing
                    and not self._emergency_latched,
                max_concurrency=integer(self.settings, "worker_limit", 4, 1, 8))
            self.task_panel = TaskPanel(self.task_store, self.scheduler, self._task_source,
                                       authorize_callback=self._authorize_task, group_provider=self._task_groups)
        except Exception as error:
            self.task_store = None
            self.scheduler = UnavailableScheduler()
            self.task_panel = QLabel(f"Scheduling unavailable: {error}\nThe database was preserved. Check storage/permissions or restore a backup. Editing and manual runs remain available.")
            self.task_panel.setWordWrap(True)
        self.project_panel = ProjectPanel(self)
        self.project_panel.project_opened.connect(self._set_project)
        self.project_panel.source_selected.connect(self._project_search_result)
        self.debugger_panel = DebuggerPanel()
        self.debugger_panel.start_requested.connect(self.debug_script)
        self.debugger_panel.command_requested.connect(self._debug_command)
        self.debugger_panel.stop_requested.connect(lambda run: self.runtime.cancel(run))
        self.debugger_panel.runs.currentIndexChanged.connect(lambda _: self._show_execution_line())
        self.debugger_panel.breakpoints_changed.connect(self._set_debug_breakpoints)
        self.debugger_panel.source_requested.connect(self._debug_source)
        self.editor.breakpoints_changed.connect(self._debug_breakpoints)
        self.shell = WorkspaceShell(self)
        self.shell.settings_panel.log_path.setText("Application event log: " + (str(self.event_log_path) if self.event_log_path else "unavailable; check local data permissions"))
        self.shell.settings_panel.check_ocr_requested.connect(self.check_ocr)
        self.shell.settings_panel.check_health_requested.connect(self.check_health)
        self.setCentralWidget(self.shell)
        from app.ui.draft_recovery import DraftRecoveryController
        try:
            self.draft_recovery = DraftRecoveryController(self, data_root)
        except (OSError, ValueError) as error:
            self.draft_recovery = None
            self.log(f"Draft recovery storage unavailable; source files preserved: {error}")
        self._connection_wizard = None
        self._diagnostic_connection = None
        self.device_manager.wizard_requested.connect(self.open_connection_wizard)
        self.project_panel.set_project(self.project_root)
        self.task_timer = QTimer(self)
        self.task_timer.timeout.connect(self._scheduler_tick)
        self.task_timer.start(500)
        self.device_manager.settings_requested.connect(lambda: self.show_workspace("settings"))
        self.editor.set_project_root(self.project_root)
        self.refresh_assets()
        self.editor.set_text('# Choose your phone in the selector above.\nprint(getDevice())\n# Capture an image with Screenshot, then click("start.png")\n')
        self.saved_source = self.editor.source
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        # Legacy dock layout is retained in settings but no longer constrains
        # the workspace shell. Splitter preferences have a versioned namespace.
        last_workspace = self.settings.value("last_workspace", "studio")
        self.shell.switch("studio" if last_workspace == "settings" else last_workspace)
        self.control_timer = QTimer(self)
        self.control_timer.timeout.connect(self._sync_controls)
        self.control_timer.start(150)
        self.simulation_timer = QTimer(self)
        self.simulation_timer.timeout.connect(self.update_simulations)
        self.simulation_timer.start(150)
        self.host_metrics = HostMetrics()
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self._update_host_metrics)
        self.metrics_timer.start(1000)
        self._set_editor_appearance()
        self.live_panel.fps.setValue(integer(self.settings, "stream_fps", 30, 1, 60))
        self.live_panel.bitrate.setValue(integer(self.settings, "stream_bitrate", 8, 1, 32))
        self.live_panel.max_size.setValue(integer(self.settings, "stream_size", 1280, 256, 4096))
        self.device_manager.redact_serials.setChecked(self.settings.value("redact_diagnostics", True, type=bool))
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.capture_selected)
        self.preview_timer.start(1000)
        self.stream_timer = QTimer(self)
        self.stream_timer.timeout.connect(self._update_live_frames)
        self.stream_timer.start(33)
        self.discovery_timer = QTimer(self)
        self.discovery_timer.timeout.connect(self.refresh_devices)
        if discover:
            self.discovery_timer.start(integer(self.settings, "discovery_seconds", 3, 1, 15) * 1000)
            if not self.settings.value("first_run_wizard_seen", False, type=bool):
                QTimer.singleShot(600, self._show_first_run_wizard)
        if discover:
            QTimer.singleShot(0, self.refresh_devices)

    def _dock(self, title, name, widget, area):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setTitleBarWidget(QWidget())
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.docks[name] = dock
        return dock

    def show_workspace(self, name):
        name = {"phone": "devices", "events": "monitor"}.get(name, name)
        if name == "settings":
            self.show_settings()
            return
        if hasattr(self, "shell"):
            self.shell.switch(name)
            self._sync_controls()

    def show_settings(self):
        if not hasattr(self, "_settings_dialog"):
            dialog = self._settings_dialog = QDialog(self)
            dialog.setWindowTitle("Settings — Android Automation Studio")
            dialog.resize(900, 600)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(0, 0, 0, 0)
            panel = self.shell.settings_panel
            self.shell.stack.removeWidget(panel)
            layout.addWidget(panel)
            panel.save_requested.connect(lambda values: dialog.accept() if self.apply_settings(values) else None)
        self._settings_dialog.show()
        self.shell.settings_panel.show()
        self._settings_dialog.raise_()

    def open_preview(self):
        self.show_workspace("devices")
        self.shell.reveal_preview()
        if self.streams.status(self.selected_serial()).state not in ("starting", "streaming"):
            self.start_live()

    def _action(self, menu, title, callback, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
            self.addAction(action)
            if shortcut in ("Ctrl+Shift+P", "Ctrl+Shift+F12"):
                action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        menu.addAction(action)
        return action

    def _build_actions(self):
        self.actions = {}
        file_menu = self.menuBar().addMenu("&File")
        self.actions["new"] = self._action(file_menu, "New Python script", self.new_script, QKeySequence.StandardKey.New)
        self.actions["open"] = self._action(file_menu, "Open Python script…", self.open_script, QKeySequence.StandardKey.Open)
        self.actions["save"] = self._action(file_menu, "Save script", self.save_script, QKeySequence.StandardKey.Save)
        self._action(file_menu, "Save script as…", lambda: self.save_script(save_as=True), QKeySequence.StandardKey.SaveAs)
        self._action(file_menu, "Choose project image library…", self.choose_project)
        execution_menu = self.menuBar().addMenu("&Execution")
        self.run_action = self._action(execution_menu, "Run trusted script…", self.run_script, "F5")
        self.actions["run"] = self.run_action
        self.actions["debug"] = self._action(execution_menu, "Debug trusted script…", self.debug_script, "F9")
        self.actions["debug"].setVisible(False)
        self.actions["pause"] = self._action(execution_menu, "Pause run", lambda: self._control_run("pause"), "F6")
        self.actions["resume"] = self._action(execution_menu, "Resume run", lambda: self._control_run("resume"), "Shift+F6")
        self.actions["stop"] = self._action(execution_menu, "Stop run", lambda: self._control_run("cancel"), "Shift+F5")
        self.actions["run_selected"] = self._action(execution_menu, "Run editor on selected phones…", self.run_selected_scripts, "Ctrl+F5")
        self.actions["assign"] = self._action(execution_menu, "Assign Python file to current phone…", self.assign_script)
        self.actions["run_assigned"] = self._action(execution_menu, "Run assigned files on selected phones…", self.run_assigned_scripts)
        self._action(execution_menu, "Emergency stop", self.emergency_stop, "Ctrl+Shift+F12")
        self.reset_stop_action = self._action(execution_menu, "Reset emergency stop", self.reset_emergency_stop)
        self.reset_stop_action.setEnabled(False)
        devices_menu = self.menuBar().addMenu("&Devices")
        self._action(devices_menu, "Start Demo Session", self.start_demo, "Ctrl+Shift+D")
        self._action(devices_menu, "Reset Demo", self.reset_demo)
        self._action(devices_menu, "Refresh devices", self.refresh_devices)
        self._action(devices_menu, "Diagnose Connection", self.diagnose_connection)
        self.actions["capture"] = self._action(devices_menu, "Capture image region…", self.capture_region, "Ctrl+Shift+C")
        self.actions["capture_png"] = self._action(devices_menu, "Capture PNG…", self.save_capture)
        self.actions["home"] = self._action(devices_menu, "Home", lambda: self._key("HOME"))
        self.actions["back"] = self._action(devices_menu, "Back", lambda: self._key("BACK"))
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
            self._action(insert_menu, label, lambda checked=False, text=code: self.insert_code(text))
        toolbar = QToolBar("Context actions", self)
        toolbar.setObjectName("contextToolbarV2")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # File and run actions retain shortcuts; the Stitch header is the only
        # visible toolbar.
        toolbar.hide()
        for key, glyph in (("new", "add"), ("open", "folder"), ("save", "studio"),
                           ("run", "run"), ("pause", "pause"), ("resume", "run"),
                           ("stop", "stop"), ("capture", "visual")):
            action = self.actions[key]
            action.setIcon(icon(glyph))
            action.setIconText({"new": "New", "open": "Open", "save": "Save", "run": "Run", "pause": "Pause", "resume": "Resume", "stop": "Stop", "capture": "Capture target"}[key])
            toolbar.addAction(action)
            if key in ("save", "stop"):
                toolbar.addSeparator()
        toolbar.addAction(self.reset_stop_action)
        view_menu = self.menuBar().addMenu("&View")
        self._action(view_menu, "Reset layout", lambda: self.shell.reset())
        self._action(view_menu, "Command palette…", self.command_palette, "Ctrl+Shift+P")
        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "Dependency health…", self.check_health)
        self._action(help_menu, "Export Bug Report…", self.export_bug_report)
        self._action(help_menu, "Connection troubleshooting", self.diagnose_connection)
        self._action(help_menu, "Connect a phone…", self.open_connection_wizard)
        self._action(help_menu, "Scripting capabilities", lambda: QMessageBox.information(self, "Alpha capabilities",
            "Available: Python image automation, Monaco, serial-bound workers, ADB/scrcpy previews, capture, recognition, diagnostics and studio-control recording.\n\n"
            "Offline simulation, recognition, optional Tesseract OCR, debugger, persistent tasks and project archives are available. Scheduled source requires explicit session approval. Real phones and Windows still require acceptance validation. See docs/ALPHA_COMPLETION.md."))

    def log(self, message):
        self.logs.appendPlainText(time.strftime("%H:%M:%S ") + str(message))
        self.statusBar().showMessage(str(message).splitlines()[0][:300], 8000)

    def notify(self, message):
        self.log(message)
        if hasattr(self, "shell"):
            self.shell.notification.setText(str(message))
            self.shell.notification.show()

    def insert_code(self, source):
        if not self.editor.is_ready:
            self.notify("Monaco is still loading. If it reports missing assets, run python tools/fetch_monaco.py.")
            return
        self.editor.insert(source)

    def start_demo(self):
        if self._closing or self._demo_pending:
            return
        self._demo_pending = True
        scenario, delay = self.simulation_panel.options()
        self.simulation_panel.status.setText("Creating an explicit offline session and a new demo project…")
        root = Path(os.environ.get("STUDIO_DATA_DIR") or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "AndroidAutomationStudio") / "demo-projects"
        def operation():
            info = self.simulations.create(scenario, delay)
            try:
                project, script = create_demo_project(root, info.serial, scenario)
            except Exception:
                self.simulations.stop(info.serial)
                raise
            return info, project, script
        def finished(result, error):
            self._demo_pending = False
            if error:
                self.notify(f"Demo could not start: {error}")
                return
            info, project, script = result
            self._demo_projects[info.serial] = project
            self.shell.documents.add(script, script.read_text(encoding="utf-8"), project)
            self.select_simulation(info.serial)
            self.show_workspace("studio")
            self.shell.reveal_preview()
            self.simulation_panel.status.setText(f"{info.name} · {SIMULATION_LABEL}\nProject: {project}")
            self.log(f"{SIMULATION_LABEL} · {info.serial} · {info.scenario}")
        self._submit(operation, finished)

    def open_demo_example(self):
        serial = self.active_simulation
        info = self.simulations.get(serial)
        root = self._demo_projects.get(serial)
        if not info or not root:
            self.notify("Select an active demo before opening its example.")
            return
        self.open_script_path(root / "scripts" / (info.scenario + ".py"))
        self.show_workspace("studio")

    def select_simulation(self, serial):
        info = self.simulations.get(serial)
        if info is None or not info.available:
            self.notify("This simulation is stopped. Start a new session explicitly.")
            return
        self.active_simulation = serial
        self._preview_modes[serial] = "simulation"
        self.preview.clear()
        self._refresh_device_details()
        self._show_execution_line()
        self.update_simulations()
        self._sync_controls()

    def select_real_device(self, serial):
        self.active_simulation = None
        blocker = QSignalBlocker(self.devices)
        row = next((row for row in range(self.devices.count()) if self.devices.item(row).data(Qt.ItemDataRole.UserRole).serial == serial), -1)
        self.devices.setCurrentRow(row)
        del blocker
        self._selection_changed(self.devices.currentItem(), None)
        self._sync_controls()

    def reset_demo(self):
        serial = self.active_simulation
        if not serial or self._demo_pending:
            self.notify("Select an active simulated session to reset.")
            return
        self._revoke_scheduled_device(serial)
        self.runtime.invalidate_device(serial)
        self._connection_token(serial).set()
        self.preview.clear()
        if self.recorder.serial == serial and self.recorder.state != "stopped":
            self.stop_recording("Simulation reset invalidated this recording connection")
        self._demo_pending = True
        scenario, delay = self.simulation_panel.options()
        def finished(info, error):
            self._demo_pending = False
            if error:
                self.notify(error)
                return
            self._connection_tokens[serial] = threading.Event()
            self._preview_modes[serial] = "simulation"
            self.simulation_panel.status.setText(f"Reset {info.name} · {info.scenario}; old scripts cancelled. Use Open scenario script for this example. Project assets were preserved.\n{SIMULATION_LABEL}")
            self.update_simulations()
            self._sync_controls()
        self._submit(lambda: self.simulations.reset(serial, scenario, delay), finished)

    def stop_demo(self):
        serial = self.active_simulation
        if not serial or self._demo_pending:
            return
        self._revoke_scheduled_device(serial)
        self.runtime.invalidate_device(serial)
        self._connection_token(serial).set()
        self._preview_modes[serial] = "stopped"
        self.preview.clear()
        if serial in self.live_panel.tiles:
            self.live_panel.tiles[serial][1].clear()
        if self.recorder.serial == serial and self.recorder.state != "stopped":
            self.stop_recording("Simulation stopped")
        self._demo_pending = True
        def finished(result, error):
            self._demo_pending = False
            self.simulation_panel.status.setText(str(error) if error else "Demo disconnected. No physical device was changed; project files remain saved.")
            self._sync_controls()
        self._submit(lambda: self.simulations.stop(serial), finished)

    def update_simulations(self):
        if self._closing:
            return
        for info in self.simulations.snapshot():
            serial = info.serial
            if not info.available or serial in self._simulation_pending or self._preview_modes.get(serial) != "simulation":
                continue
            token = self._connection_token(serial)
            if token.is_set():
                continue
            self._simulation_pending.add(serial)
            transport = SimulationTransport(self.simulations.client(serial))
            def finished(result, error, identity=serial, connection=token, name=info.name):
                self._simulation_pending.discard(identity)
                if connection.is_set() or self._preview_modes.get(identity) != "simulation":
                    return
                if error:
                    self.log(error)
                    return
                frame, state = result
                view = self.live_panel.tile(identity)
                self.live_panel.tiles[identity][0].setTitle(name + " · SIMULATED")
                if not view.property("controlsConnected"):
                    view.gesture.connect(lambda start, end, ms, target=identity, widget=view: self._gesture_on(target, widget, start, end, ms))
                    view.double_tap.connect(lambda x,y,target=identity,widget=view: self._double_tap(target, widget, x,y))
                    view.setProperty("controlsConnected", True)
                view.set_frame(frame)
                self.live_panel.update_status(identity, SIMULATION_LABEL + " · " + state["screen"], self.selected_serial())
                if identity == self.selected_serial():
                    self.preview.set_frame(frame)
                    self.live_panel.status.setText(f"{name} · SIMULATED · {state['screen']}")
                    self.live_panel.status.setToolTip(identity + "\n" + SIMULATION_LABEL)
                    self.live_panel.geometry_label.setText(f"Simulation {frame.width} × {frame.height} · {state['screen']} · {state['actions']} state actions")
            self._submit(lambda client=transport: (client.frame(), client.client.state()), finished)

    def new_script(self):
        try:
            self.shell.documents.add(None, "", self.project_root)
            self.show_workspace("studio")
        except ValueError as error:
            self.notify(error)

    def command_palette(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Commands")
        dialog.resize(600, 420)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Type a command…")
        commands = QListWidget()
        layout.addWidget(search)
        layout.addWidget(commands)
        # QAction ownership is the window; menu actions cover operations without shortcuts.
        actions = [action for action in self.findChildren(QAction) if action.text() and not action.isSeparator() and action.menu() is None]
        def filter_commands(text):
            commands.clear()
            for action in actions:
                title = action.text().replace("&", "")
                if text.lower() in title.lower():
                    item = QListWidgetItem(title + ("  ·  " + action.shortcut().toString() if not action.shortcut().isEmpty() else ""))
                    item.setData(Qt.ItemDataRole.UserRole, action)
                    if not action.isEnabled():
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                        item.setToolTip(action.toolTip())
                    commands.addItem(item)
            if commands.count():
                commands.setCurrentRow(0)
        def invoke(item=None):
            item = item or commands.currentItem()
            if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                action = item.data(Qt.ItemDataRole.UserRole)
                dialog.accept()
                action.trigger()
        search.textChanged.connect(filter_commands)
        search.returnPressed.connect(invoke)
        commands.itemDoubleClicked.connect(invoke)
        filter_commands("")
        search.setFocus()
        dialog.exec()

    def _set_editor_appearance(self):
        if hasattr(self.editor, "set_appearance"):
            self.editor.set_appearance(theme_name(self.settings), integer(self.settings, "editor_font_size", 14, 10, 24))

    def apply_settings(self, values):
        panel = self.shell.settings_panel
        tool_changed = (values["adb_path"] != self.settings.value("adb_path", "")
                        or values["scrcpy_server_path"] != self.settings.value("scrcpy_server_path", ""))
        if tool_changed and (self.jobs or self._diagnostic_busy or self._network_pending
                or self.pending_controls or self.pending_runs or any(r.exitcode is None for r in self.run_states)
                or self._capture_dialogs or any(s.state in ("starting", "streaming", "stopping") for s in self.streams.statuses().values())):
            panel.result.setText("Stop live previews and runs, and wait for pending operations before changing Android tools.")
            return False
        selected_adb = values["adb_path"]
        invalid_adb = bool(selected_adb and (not Path(selected_adb).is_file()
                           or (sys.platform == "win32" and Path(selected_adb).name.lower() != "adb.exe")))
        if tool_changed:
            new_adb = AdbClient(adb_executable(values["adb_path"]))
            # The next diagnostic run verifies executable/version/permissions;
            # selecting a path is configuration, never a connection success.
            self.streams.close(timeout=0)
            self.adb = new_adb
            self._discovery_checked = False
            self._last_discovery_error = None
            self.capture = CaptureService(new_adb)
            self.streams = StreamManager(new_adb)
            configured = os.environ.get("STUDIO_SCRCPY_SERVER") or values["scrcpy_server_path"]
            if configured:
                self.streams.server_path = Path(configured).expanduser()
            self._apply_device_states(self.registry.mark_unknown())
        for key, value in values.items():
            self.settings.setValue(key, value)
        self.settings.sync()
        apply_theme(QApplication.instance(), values["theme"])
        self._set_editor_appearance()
        self.live_panel.fps.setValue(values["stream_fps"])
        self.live_panel.bitrate.setValue(values["stream_bitrate"])
        self.live_panel.max_size.setValue(values["stream_size"])
        self.discovery_timer.setInterval(values["discovery_seconds"] * 1000)
        self.device_manager.redact_serials.setChecked(values["redact_diagnostics"])
        panel.effective_path.setText("Currently selected: " + self.adb.executable)
        panel.result.setText("Selected ADB is missing or is not adb.exe; device discovery will fail until you choose platform-tools adb.exe."
                             if invalid_adb else "Settings saved. Worker limit applies at next launch. Use Diagnose Connection to verify Android tools.")
        if tool_changed:
            self.refresh_devices()
        return True

    def _sync_controls(self):
        if not hasattr(self, "shell") or self._closing:
            return
        serial = self.selected_serial()
        devices = self.registry.snapshot()
        discovery_state = ("checking" if self.discover_pending else "failed" if self._last_discovery_error
                           else "ready" if self._discovery_checked else "not checked")
        self.device_manager.update_system_status(connection_overview(
            self.adb.executable, discovery_state, devices, self._selected_identity(),
            demo=bool(self.active_simulation),
            active_runs=sum(run.exitcode is None for run in self.run_states),
            last_error=self._last_discovery_error))
        available = bool(serial and self._device_available(serial))
        idle = available and not self.busy(serial)
        can_input = idle and not self._emergency_latched
        self.device_manager.set_available(available, not idle)
        self.run_action.setEnabled(can_input and self.editor.is_ready)
        self.actions["debug"].setEnabled(can_input and self.editor.is_ready)
        self.debugger_panel.start_button.setEnabled(can_input and self.editor.is_ready)
        phones = self._selected_phones()
        group_idle = bool(phones) and all(not self.busy(phone) for phone in phones) and not self._emergency_latched
        self.actions["run_selected"].setEnabled(group_idle and self.editor.is_ready)
        self.actions["assign"].setEnabled(available)
        self.actions["run_assigned"].setEnabled(group_idle and all(phone in self.assignments for phone in phones) and self.editor.is_ready)
        self.actions["home"].setEnabled(can_input)
        self.actions["back"].setEnabled(can_input)
        for key in ("capture", "capture_png"):
            self.actions[key].setEnabled(available)
            self.actions[key].setToolTip("Capture from the selected Android phone" if available else "Connect and select an authorized phone first")
        run_id = self._active_run_id()
        active = next((run for run in self.run_states if run.run_id == run_id and run.exitcode is None), None)
        self.actions["pause"].setEnabled(bool(active and active.state == "running"))
        self.actions["resume"].setEnabled(bool(active and active.state == "paused"))
        self.actions["stop"].setEnabled(active is not None)
        self.shell.start_button.setEnabled(self.run_action.isEnabled())
        self.shell.stop_button.setEnabled(self.actions["stop"].isEnabled())
        self.shell.pause_button.setEnabled(self.actions["pause"].isEnabled() or self.actions["resume"].isEnabled())
        self.shell.pause_button.setText("Resume" if self.actions["resume"].isEnabled() else "Pause")
        self.shell.coordinate_button.setEnabled(available and not self.capture_pending)
        self.shell.screenshot_button.setEnabled(self.actions["capture"].isEnabled())
        self.reset_stop_action.setVisible(self._emergency_latched)
        self.shell.sync_devices()
        self.shell.welcome.hide()
        self.live_panel.set_control_state(available, can_input, self.streams.status(serial).state if serial else "stopped")
        self.live_panel.start_all_action.setEnabled(any(device.available for device in self.registry.snapshot()))
        self.recorder_panel.set_control_state(can_input, self.recorder.state)
        self.visual_tools.set_control_state(available, self.editor.is_ready)
        simulated = is_simulation(self._selected_identity())
        self.shell.simulation_notice.setVisible(simulated)
        self.simulation_panel.set_active(simulated and available and not self._demo_pending)
        self.device_manager.reconnect_button.setEnabled(not simulated)
        self.live_panel.start_button.setText("Resume demo" if simulated else "Start live")
        self.live_panel.stop_button.setText("Pause" if simulated else "Stop")
        self.live_panel.configure.setEnabled(not simulated)
        self.live_panel.configure.setToolTip("Encoder quality applies to real scrcpy video. Demo previews are locally rendered state." if simulated else "Configure the next scrcpy stream")
        if simulated:
            self.live_panel.set_control_state(available, can_input, "streaming" if self._preview_modes.get(serial) == "simulation" else "stopped")
            self.live_panel.start_all_action.setEnabled(False)
            self.live_panel.fallback_action.setEnabled(False)
            self.live_panel.quality.hide()
        self._sync_connection_wizard()

    def _update_host_metrics(self):
        sample = self.host_metrics.sample()
        cpu = f"{sample['cpu_percent']:.1f}%" if sample["cpu_percent"] is not None else "collecting"
        memory = f"{sample['resident_bytes'] / 1048576:.1f} MiB" if sample["resident_bytes"] is not None else "unavailable"
        active = sum(run.exitcode is None for run in self.run_states)
        self.shell.metrics.setText(f"Parent process • CPU {cpu} (one core = 100%) • Resident memory {memory}\n"
                                   f"{active} active workers • {len(self.jobs)} pending operations. Worker/WebEngine child usage is not included.")

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
        if error and self.event_log:
            self.event_log.warning("Background operation failed; check the relevant workbench status")
        if callback is not None and not self._closing:
            callback(result, error)

    def selected_serial(self):
        if self.active_simulation:
            info = self.simulations.get(self.active_simulation)
            return info.serial if info and info.available else None
        item = self.devices.currentItem()
        if item:
            device = item.data(Qt.ItemDataRole.UserRole)
            return device.serial if device.available else None
        return None

    def busy(self, serial):
        return (serial in self.pending_controls or serial in self.pending_runs.values()
                or (self._diagnostic_busy and serial == self._diagnostic_serial)
                or any(r.serial == serial and r.exitcode is None for r in self.run_states))

    def refresh_devices(self):
        if self.discover_pending or self._closing:
            return
        self.discover_pending = True
        client = self.adb
        def finished(devices, error):
            self.discover_pending = False
            if self._closing:
                return
            if client is not self.adb:
                # Settings changed while the old executable was still running.
                # Its reply cannot establish the state of the new ADB server.
                self.refresh_devices()
                return
            self._discovery_checked = True
            failure_message = None
            if error:
                self.log(error)
                self._last_discovery_error = str(error)[:1000]
                observed = self.registry.mark_unknown()
                failure_message = (f"ADB discovery failed using {self.adb.executable}: {error}\n"
                                   "Open Settings to choose adb.exe, then Diagnose Connection. " + SOLUTIONS['discovery'])
            else:
                observed = self.registry.update(devices)
                self._last_discovery_error = None
            log_state = ("failed",) if error else tuple((device.serial, device.state) for device in devices)
            if self.event_log and log_state != self._discovery_log_state:
                if error:
                    self.event_log.warning("ADB discovery failed; see connection diagnostics")
                else:
                    self.event_log.info("ADB discovery changed; authorized=%d total=%d", sum(d.available for d in devices), len(devices))
            self._discovery_log_state = log_state
            self._apply_device_states(observed)
            # Read selection at completion: discovery must not undo user input
            # made while ADB was working, including multiple selected phones.
            selected = self._selected_identity()
            selected_serials = {item.data(Qt.ItemDataRole.UserRole).serial for item in self.devices.selectedItems()}
            blocker = QSignalBlocker(self.devices)
            self.devices.clear()
            selected_item = None
            for device in observed:
                item = QListWidgetItem(self.device_manager.caption(device))
                item.setData(Qt.ItemDataRole.UserRole, device)
                item.setToolTip(f"ADB serial: {device.serial}\nAssigned script: {self.assignments.get(device.serial, 'none')}")
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
            if selected is not None:
                for row in range(self.devices.count()):
                    item = self.devices.item(row)
                    item.setSelected(item.data(Qt.ItemDataRole.UserRole).serial in selected_serials)
            del blocker
            self.device_manager.update_devices(observed)
            self._refresh_device_details()
            if failure_message:
                self.device_manager.connection_status.setText(failure_message)
                self.device_manager.empty_state.setText(failure_message)
                self.device_manager.summary.setText("ADB discovery failed; device state is unknown.")
            else:
                self.device_manager.empty_state.setText("No phones detected\n\nConnect a USB data cable and authorize debugging, or use Wireless debugging.\n\nUse Diagnose Connection if ADB cannot see the phone.")
            self.device_manager.set_available(bool(self.selected_serial()), self.busy(self.selected_serial()))
            if self._connection_confirmation is not None:
                endpoint = self._connection_confirmation
                self._connection_confirmation = None
                found = next((device for device in observed if device.serial == endpoint), None)
                if not error and found and found.available:
                    self._verify_connection(endpoint)
                else:
                    message = f"Connection NOT verified for {endpoint}: {error or (found.state if found else 'not discovered')}. Run Diagnose Connection."
                    self._connection_problem = message
                    self.device_manager.connection_status.setText(message)
                    self.device_manager.add_history(message)
            if not observed:
                message = (f"No devices detected by {self.adb.executable}. Connect a USB data cable, unlock the phone "
                           "and authorize debugging, then Refresh. If standalone scrcpy sees it, choose scrcpy's adb.exe "
                           "in Settings and run Diagnose Connection.")
                if self._discovery_message != message:
                    self.log(message)
                self._discovery_message = message
                if not error and not self._connection_problem:
                    self.device_manager.connection_status.setText(message)
            if selected != self._selected_identity():
                self._selection_changed(self.devices.currentItem(), None)
        self._submit(client.devices, finished)

    def _refresh_device_details(self):
        serial = self._selected_identity()
        if is_simulation(serial):
            self.device_manager.details.setText(SIMULATION_LABEL + "\n" + serial + "\nADB authorization does not apply.")
            return
        self.device_manager.android_versions = self._android_versions
        self.device_manager.show_device(self.registry.get(serial) if serial else None,
                                        script=self.assignments.get(serial), screen=self._screen_info.get(serial))

    def _verify_connection(self, serial):
        token = self._connection_token(serial)
        self.device_manager.connection_status.setText(f"Authorized transport discovered: {serial}. Checking Android response…")
        def operation():
            if token.is_set() or self.adb.state(serial) != "device":
                raise RuntimeError("The discovered device is no longer available")
            return self.adb.android_version(serial)
        def finished(version, error):
            if error or token.is_set():
                message = f"Connection NOT verified for {serial}: {error or 'connection changed'}. Use Diagnose Connection."
                self._connection_problem = message
            else:
                message = f"Connected and authorized: {serial} · Android {version}; device query succeeded."
                self._connection_problem = None
                self._android_versions[serial] = version
            self.device_manager.connection_status.setText(message)
            self.device_manager.add_history(message)
            self.log(message)
        self._submit(operation, finished)

    def diagnose_connection(self):
        self.show_workspace("devices")
        if is_simulation(self._selected_identity()):
            self.device_manager.tabs.setCurrentWidget(self.simulation_panel)
            self.notify(SIMULATION_LABEL + ". Select a physical device for ADB diagnostics.")
            return
        self.device_manager.show_diagnostics()
        if self._diagnostic_busy or self._closing:
            return
        serial = self._selected_identity()
        if serial and self.busy(serial):
            self.device_manager.connection_status.setText("Stop the selected phone's script/control operation before diagnostics.")
            return
        self._diagnostic_busy = True
        self._diagnostic_serial = serial
        self._diagnostic_connection = self._connection_token(serial) if serial else None
        self._diagnostic_cancel = threading.Event()
        self.device_manager.diagnostic_busy(True)
        runner = ConnectionDiagnostics(self.adb, self.streams, progress=self.diagnostic_progress.emit,
                                       cancel=self._diagnostic_cancel)
        video = self.device_manager.check_video.isChecked()
        def finished(report, error):
            self._diagnostic_busy = False
            self._diagnostic_serial = None
            self.device_manager.diagnostic_busy(False)
            if error:
                self.device_manager.connection_status.setText(f"Diagnostics failed: {error}")
            else:
                self.device_manager.set_report(report)
                failed = next((step for step in report.steps if step.state == "failed"), None)
                self.device_manager.connection_status.setText(
                    f"Stopped at {failed.title}: {failed.detail}\n{failed.advice}" if failed else
                    "Diagnostics finished. Review each stage; skipped checks remain NOT VERIFIED.")
        self._submit(lambda: runner.run(serial, video=video), finished)

    def reconnect_device(self):
        serial = self._selected_identity()
        try:
            validate_endpoint(serial)
        except ValueError:
            self.device_manager.connection_status.setText("USB reconnect: check/unplug/replug the cable, unlock and authorize the phone. Refreshing discovery now. No shared ADB server will be restarted.")
            self.refresh_devices()
        else:
            self._network_action("connect", serial)

    def _network_action(self, action, endpoint, code=None):
        if self._closing or self._network_pending:
            return
        try:
            endpoint = validate_endpoint(endpoint)
        except ValueError as error:
            self.device_manager.connection_status.setText(str(error))
            return
        self._network_pending = True
        self._connection_problem = None
        self.device_manager.set_network_busy(True)
        self.device_manager.connection_status.setText(f"{action.capitalize()} in progress: {endpoint}")
        def finished(result, error):
            self._network_pending = False
            self.device_manager.set_network_busy(False)
            message = error or result
            self.device_manager.connection_status.setText(message)
            self.device_manager.add_history(message)
            self.log(message)
            if error:
                self._connection_problem = str(error)
                self.notify(f"Connection failed: {error}. Open Diagnose Connection for details.")
            if not error and action == "connect":
                self._connection_confirmation = endpoint
                self.device_manager.connection_status.setText(f"Transport acknowledged {endpoint}; checking discovery and authorization…")
            self.refresh_devices()
        operation = (lambda: self.adb.pair(endpoint, code)) if action == "pair" else lambda: getattr(self.adb, action)(endpoint)
        self._submit(operation, finished)

    def pair_device(self, endpoint):
        code, accepted = QInputDialog.getText(self, "Pair Wireless debugging",
            "Enter the six-digit code shown by Pair device with pairing code.\nThis endpoint must use the pairing port.",
            QLineEdit.EchoMode.Password)
        if accepted:
            self._network_action("pair", endpoint, code)

    def disconnect_device(self):
        serial = self._selected_identity()
        if is_simulation(serial):
            self.notify("Use Stop Demo for simulation; this button only disconnects physical Wi-Fi endpoints.")
            return
        if self._network_pending or self._closing:
            return
        try:
            validate_endpoint(serial)
        except ValueError:
            self.device_manager.connection_status.setText("Select a Wi-Fi host:port device. To disconnect USB, unplug its cable.")
            return
        # Invalidate queued work before asking ADB to remove the transport.
        self._connection_token(serial).set()
        self.runtime.invalidate_device(serial)
        self.streams.stop(serial)
        self.capture.forget(serial)
        self.preview.clear()
        self._preview_modes[serial] = "stopped"
        if self.recorder.serial == serial and self.recorder.state != "stopped":
            self.stop_recording("Wi-Fi disconnection requested")
        self._network_action("disconnect", serial)

    def start_recording(self):
        serial = self.selected_serial()
        if not serial or self.busy(serial) or self._closing or self._emergency_latched:
            self.log("Recording requires an idle authorized phone with emergency stop reset.")
            return
        if self.recorder_panel.table.rowCount():
            answer = QMessageBox.question(self, "New recording", "Replace the current recorded timeline? Insert it into a script first to keep it.")
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self.recorder.start(serial, self._device_record(serial).generation)
            frame=self.preview.frame
            if frame and frame.serial==serial:
                geometry=(getattr(frame,"source_width",frame.width),getattr(frame,"source_height",frame.height))
                self.recorder.screen_size=geometry if all(type(v)is int and v>0 for v in geometry) else None
        except ValueError as error:
            self.log(str(error))
            return
        self.recorder_panel.refresh(reset=True)
        self.show_workspace("recorder")

    def pause_recording(self):
        try:
            if self.recorder.state == "paused":
                current = self._device_record(self.recorder.serial)
                if not current or not current.available:
                    raise ValueError("Recording phone is unavailable")
                self.recorder.resume(current.serial, current.generation)
            else:
                self.recorder.pause()
            self.recorder_panel.refresh()
        except ValueError as error:
            self.log(str(error))

    def stop_recording(self, reason="Stopped by user"):
        self.recorder.stop(reason)
        self.recorder_panel.refresh()

    def insert_recording(self):
        try:
            if not self.editor.is_ready:
                raise ValueError("Wait for Monaco to load before inserting a recording")
            self.editor.insert(self.recorder_panel.source())
        except ValueError as error:
            self.log(str(error))

    def save_recording(self):
        try:
            self.recorder_panel.source()
            payload = self.recorder.session_json().encode("utf-8")
            path, _ = QFileDialog.getSaveFileName(self, "Save recorder session", str(self.project_root / "recording.json"), "Recorder session (*.json)")
            if path:
                self._atomic_write(Path(path), payload)
                self.recorder_panel.status.setText(f"Session saved: {path}. Reopening will not start replay.")
        except (ValueError, OSError) as error:
            self.recorder_panel.status.setText(str(error))

    def load_recording(self):
        if self.recorder.state != "stopped":
            self.notify("Stop recording before opening a session.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open recorder session", str(self.project_root), "Recorder session (*.json)")
        if not path:
            return
        try:
            if self.recorder_panel.table.rowCount() and QMessageBox.question(self, "Open recording", "Replace the current timeline? Save or insert it into a script first to keep it.") != QMessageBox.StandardButton.Yes:
                return
            file = Path(path)
            if file.stat().st_size > MAX_SESSION_BYTES:
                raise ValueError("Recorder sessions must be smaller than 10 MB")
            self.recorder.load_session(file.read_text(encoding="utf-8"))
            self.recorder_panel.refresh(reset=True)
            self.notify("Recording opened without executing it. Select a phone and verify screen geometry before replay.")
        except (ValueError, OSError) as error:
            self.recorder_panel.status.setText(str(error))

    def replay_recording(self):
        try:
            source = self.recorder_panel.source()
        except ValueError as error:
            self.notify(error)
            return
        serial = self.selected_serial()
        if not serial:
            self.notify("Select a replay target first."); return
        token=self._connection_token(serial)
        def checked(frame,error):
            if error or token.is_set() or self.selected_serial()!=serial:
                self.notify(error or "Replay target changed before approval"); return
            expected=self.recorder.screen_size
            if expected and expected!=(frame.width,frame.height):
                answer=QMessageBox.warning(self,"Recording geometry changed",
                    f"Recorded at {expected[0]} × {expected[1]}, selected target is {frame.width} × {frame.height}. Coordinates are not automatically rescaled. Replay anyway?",
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
                if answer!=QMessageBox.StandardButton.Yes:
                    return
            self._approve_and_run([(serial, source, "<editor>", self.project_root)])
        self._submit(lambda:self.capture_device(serial),checked)

    def convert_recorded_tap(self):
        panel=self.recorder_panel
        row=panel.table.currentRow()
        if self.recorder.state!="stopped" or row<0:
            self.notify("Stop recording and select a coordinate tap first."); return
        item=panel.table.item(row,0)
        metadata=item.data(Qt.ItemDataRole.UserRole) or {}
        evidence=metadata.get("evidence")
        if evidence is None:
            self.notify("No pre-tap screenshot exists for this step. Record with capture enabled or capture a target manually."); return
        import ast
        try:
            call=ast.parse(item.text()).body[0].value
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!="tap" or len(call.args)!=2:
                raise ValueError("Only coordinate tap(x,y) steps can be converted")
            x,y=(ast.literal_eval(argument) for argument in call.args)
            if any(type(value)is not int for value in (x,y)) or not 0<=x<evidence.size[0] or not 0<=y<evidence.size[1]:
                raise ValueError("Choose a tap with explicit integer coordinates")
        except (ValueError,SyntaxError,AttributeError,IndexError) as error:
            self.notify(error); return
        root=self.project_root
        original=item.text()
        def loaded(image,error):
            if error or image.isNull():
                self.notify(error or "Recorded screenshot could not be decoded"); return
            directory=root/"images"
            try:
                from app.projects.library import AssetLibrary
                directory=AssetLibrary(root).image_root; directory.mkdir(exist_ok=True)
            except (ValueError,OSError) as error:
                self.notify(error); return
            dialog=CaptureDialog(image,evidence.serial,parent=self,save_directory=directory)
            dialog.instructions.setText((SIMULATION_LABEL+"\n" if is_simulation(evidence.serial) else "Recorded pre-tap screenshot.\n")+"Crop a real target around the tap, save it inside this project, then the selected step becomes image-based.")
            left,top=max(0,x-40),max(0,y-25)
            from app.vision.matching import Region
            dialog.select_region(Region(left,top,min(80,image.width()-left),min(50,image.height()-top)))
            def saved(path,region):
                from app.projects.library import AssetLibrary
                from app.automation.recording import image_target_code
                try:
                    asset=AssetLibrary(root).resolve(path)
                    reference=asset.relative_to(root).as_posix()
                    code=image_target_code(original,region,reference)
                except (OSError,ValueError) as error:
                    self.notify(error); return
                def verify():
                    from app.ui.visual_tools import load_asset
                    from app.ui.capture_dialog import image_rgb
                    from app.vision.matching import find_all
                    pixels=image_rgb(load_asset(root,reference))
                    # Reject untextured/invalid crops using the real matcher contract.
                    find_all(pixels,pixels,max_results=1)
                def verified(result,error):
                    if error:
                        self.notify("Image saved; step was not replaced: "+str(error)); return
                    if self.project_root!=root or row>=panel.table.rowCount() or panel.table.item(row,0) is not item or item.text()!=original:
                        self.notify("Timeline/project changed; image saved but step was not replaced"); return
                    item.setText(code)
                    self._asset_saved(path,region)
                    panel.step_info.setText("Selected step now uses a saved image target: "+reference)
                self._submit(verify,verified)
            self._capture_dialogs.add(dialog)
            dialog.asset_saved.connect(saved)
            def finished(result):
                self._capture_dialogs.discard(dialog);dialog.deleteLater()
            dialog.finished.connect(finished);dialog.show()
        self._submit(lambda:QImage.fromData(evidence.png,"PNG"),loaded)

    def refresh_assets(self):
        if self._closing:
            return
        self._library_request += 1
        request = self._library_request
        root = self.project_root
        def finished(result, error):
            if request != self._library_request or root != self.project_root:
                return
            if error:
                self.visual_tools.status.setText(error)
                return
            self.visual_tools.set_entries(*result)
        self._submit(lambda: scan_assets(root), finished)

    def preview_asset(self, reference):
        self._thumbnail_request += 1
        request, root = self._thumbnail_request, self.project_root
        self.visual_tools.thumbnail.clear()
        if not reference:
            self.visual_tools.thumbnail.setText("Select an image to preview")
            return
        def finished(image, error):
            if request != self._thumbnail_request or root != self.project_root:
                return
            if error:
                self.visual_tools.status.setText(error)
            else:
                self.visual_tools.set_thumbnail(image)
        self._submit(lambda: load_asset(root, reference), finished)

    def insert_visual_command(self, command):
        from app.projects.library import AssetLibrary
        try:
            if not self.editor.is_ready:
                raise ValueError("Wait for Monaco to load")
            AssetLibrary(self.project_root).resolve(self.visual_tools.selected_reference())
            code = self.visual_tools.code(command)
            compile(code, "<visual command>", "exec")
            self.editor.insert(code)
        except (OSError, ValueError, TypeError, SyntaxError) as error:
            self.visual_tools.status.setText(str(error))

    def test_asset(self):
        try:
            reference = self.visual_tools.selected_reference()
            options = self.visual_tools.options()
        except (ValueError, TypeError) as error:
            self.visual_tools.status.setText(str(error))
            return
        self.capture_region(template_reference=reference, match_options=options)

    def check_ocr(self):
        panel = self.shell.settings_panel
        executable = panel.ocr_path.text().strip() or None
        panel.ocr_status.setText("Checking configured local OCR engine off the GUI thread…")
        self._submit(lambda: TesseractOCR(executable).status(),
                     lambda result,error: panel.ocr_status.setText(error or result))

    def check_health(self):
        """Probe dependencies off the GUI thread without installing anything."""
        from app.health import dependency_health
        self.notify("Checking local dependencies…")
        def finished(report, error):
            if error:
                self.notify(f"Dependency health check failed: {error}")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Dependency health · local report")
            dialog.resize(760, 560)
            layout = QVBoxLayout(dialog)
            detail = QPlainTextEdit()
            detail.setReadOnly(True)
            detail.setPlainText(json.dumps(report, indent=2, ensure_ascii=False))
            detail.setAccessibleName("Dependency checks and repair commands")
            layout.addWidget(detail)
            from app.ui.components import button
            layout.addWidget(button("Copy report", lambda: QApplication.clipboard().setText(detail.toPlainText())))
            layout.addWidget(button("Close", dialog.accept))
            dialog.exec()
        paths = {"adb_path": self.settings.value("adb_path", ""),
                 "server_path": self.settings.value("scrcpy_server_path", ""),
                 "ocr_path": self.settings.value("ocr_executable", "")}
        self._submit(lambda: dependency_health(**paths), finished)

    def export_bug_report(self):
        """Collect bounded local evidence off the GUI thread, then require review."""
        from app.health import dependency_health
        from app.ui.components import button
        self.notify("Preparing local bug report…")
        paths = {"adb_path": self.settings.value("adb_path", ""),
                 "server_path": self.settings.value("scrcpy_server_path", ""),
                 "ocr_path": self.settings.value("ocr_executable", "")}
        devices = self.registry.snapshot()
        diagnostics = self.device_manager.report
        adb_path = self.adb.executable
        log_path = self.event_log_path
        last_error = self._last_discovery_error

        def finished(report, error):
            if error:
                self.notify(f"Bug report could not be prepared: {error}")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Review Bug Report before saving")
            dialog.resize(800, 600)
            layout = QVBoxLayout(dialog)
            detail = QPlainTextEdit(report)
            detail.setAccessibleName("Editable, redacted bug report for review")
            layout.addWidget(detail)

            def save():
                path, _ = QFileDialog.getSaveFileName(dialog, "Save reviewed bug report", "studio-bug-report.json", "JSON (*.json);;Text (*.txt)")
                if not path:
                    return
                output = QSaveFile(path)
                if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                    QMessageBox.warning(dialog, "Bug report export failed", output.errorString())
                    return
                data = detail.toPlainText().encode("utf-8")
                if output.write(data) != len(data) or not output.commit():
                    output.cancelWriting()
                    QMessageBox.warning(dialog, "Bug report export failed", output.errorString())
                    return
                dialog.accept()
                self.notify("Bug report saved. Review it before sharing.")

            layout.addWidget(button("Save reviewed report…", save))
            layout.addWidget(button("Close", dialog.reject))
            dialog.exec()

        self._submit(lambda: bug_report(adb_path=adb_path, health=dependency_health(**paths, native=False),
                                        devices=devices, diagnostics=diagnostics, log_path=log_path,
                                        last_error=last_error), finished)

    def compare_external_adb(self):
        from app.devices.comparison import compare_adb
        from app.ui.components import button
        path, _ = QFileDialog.getOpenFileName(self, "Choose external Android platform-tools adb.exe", str(Path.home()), "ADB executable (adb adb.exe);;All files (*)")
        if not path:
            return
        self.notify("Comparing Studio and external ADB; this may take a few seconds…")
        current = self.adb.executable

        def finished(report, error):
            if error:
                self.notify(f"ADB comparison failed: {error}")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Studio and external ADB comparison")
            dialog.resize(760, 500)
            layout = QVBoxLayout(dialog)
            detail = QPlainTextEdit(report)
            detail.setReadOnly(True)
            layout.addWidget(detail)
            layout.addWidget(button("Copy comparison (review first)", lambda: QApplication.clipboard().setText(detail.toPlainText())))
            layout.addWidget(button("Close", dialog.accept))
            dialog.exec()

        self._submit(lambda: compare_adb(current, path), finished)

    def open_connection_wizard(self):
        from app.ui.connection_wizard import ConnectionWizard
        if self._connection_wizard is None:
            wizard = self._connection_wizard = ConnectionWizard(self)
            wizard.refresh_requested.connect(self.refresh_devices)
            wizard.device_selected.connect(self.select_real_device)
            wizard.diagnose_requested.connect(self.diagnose_connection)
            wizard.preview_requested.connect(self.open_preview)
            wizard.settings_requested.connect(lambda: self.show_workspace("settings"))
            wizard.health_requested.connect(self.check_health)
            wizard.compare_adb_requested.connect(self.compare_external_adb)
            wizard.demo_requested.connect(lambda: (wizard.close(), self.start_demo()))
            wizard.wifi_requested.connect(lambda: self.show_workspace("devices"))
            wizard.harmless_test_requested.connect(self._wizard_home)
        self._connection_wizard.show()
        self._connection_wizard.raise_()
        self._sync_connection_wizard()

    def _show_first_run_wizard(self):
        if self._closing or self.settings.value("first_run_wizard_seen", False, type=bool):
            return
        self.settings.setValue("first_run_wizard_seen", True)
        self.settings.sync()
        self.open_connection_wizard()

    def _wizard_home(self, serial):
        token = self._diagnostic_connection
        report = self.device_manager.report
        if (serial != self.selected_serial() or is_simulation(serial) or not self._device_available(serial)
                or self._emergency_latched or self.busy(serial) or token is None or token.is_set()
                or self._connection_token(serial) is not token or report is None or report.verified_serial != serial):
            self.notify("Select the same idle verified Android phone before testing Home.")
            return
        self._control(serial, lambda: self.adb.key(serial, "HOME"), recorded="home()")

    def _sync_connection_wizard(self):
        wizard = getattr(self, "_connection_wizard", None)
        if wizard is None or not wizard.isVisible():
            return
        serial = self.selected_serial()
        report = self.device_manager.report
        token = self._diagnostic_connection
        current = bool(serial and not is_simulation(serial) and token is not None and not token.is_set()
                       and self._connection_token(serial) is token
                       and report and report.verified_serial == serial)
        frame = self.streams.latest(serial) if serial and not is_simulation(serial) else None
        live = bool(frame and frame.serial == serial and time.monotonic() - frame.captured_at < 3
                    and self._preview_modes.get(serial) == "live")
        wizard.update_state(self.registry.snapshot(), serial, report=report, report_current=current,
                            adb_path=self.adb.executable, discovery_error=self._last_discovery_error,
                            discovery_pending=self.discover_pending, discovery_checked=self._discovery_checked,
                            preview_ready=live, busy=self._diagnostic_busy or self.discover_pending
                            or self._network_pending or self._emergency_latched
                            or bool(serial and self.busy(serial)))

    def inspect_recognition(self):
        serial = self.selected_serial()
        root = self.project_root
        script = self.path
        try:
            reference = self.visual_tools.selected_reference()
        except ValueError:
            reference = ""
        def show(image,error,source):
            if error:
                self.notify(error); return
            dialog = RecognitionInspector(image,source,root,ocr_executable=self.settings.value("ocr_executable", "") or None,
                                          reference=reference,parent=self)
            self._capture_dialogs.add(dialog)
            dialog.code_ready.connect(lambda code: self.insert_code(code) if self.path == script else self.notify("Document changed; reopen the inspector before inserting code."))
            def finished(result):
                self._capture_dialogs.discard(dialog); dialog.deleteLater()
            dialog.finished.connect(finished)
            dialog.show()
        if serial:
            token = self._connection_token(serial)
            def operation():
                frame = self.capture_device(serial)
                if token.is_set():
                    raise RuntimeError("Connection changed during inspector capture")
                return QImage.fromData(frame.png, "PNG")
            source = SIMULATION_LABEL if is_simulation(serial) else "ADB screenshot · " + serial
            self._submit(operation,lambda result,error: show(result,error,source))
        else:
            filename,_ = QFileDialog.getOpenFileName(self,"Open screenshot for offline recognition",str(root),"Images (*.png *.jpg *.jpeg *.bmp *.webp)")
            if filename:
                path = Path(filename).resolve()
                self._submit(lambda: load_asset(path.parent,path.name),lambda result,error: show(result,error,"LOCAL SCREENSHOT — no device actions · " + path.name))

    def _connection_token(self, serial):
        return self._connection_tokens.setdefault(serial, threading.Event())

    def _selected_identity(self):
        if self.active_simulation:
            return self.active_simulation
        item = self.devices.currentItem()
        return item.data(Qt.ItemDataRole.UserRole).serial if item else None

    def _apply_device_states(self, devices):
        for device in devices:
            signature = (device.generation, device.state)
            if (self._observed_generations.get(device.serial) == signature
                    and not (device.available and self._connection_token(device.serial).is_set())):
                continue
            self._observed_generations[device.serial] = signature
            if not device.available:
                self._revoke_scheduled_device(device.serial)
                self._screen_info.pop(device.serial, None)
                self._android_versions.pop(device.serial, None)
                if self.recorder.serial == device.serial and self.recorder.state != "stopped":
                    self.stop_recording(f"Device {device.state}; reconnect and explicitly start a new recording")
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

    def _device_record(self, serial):
        return self.simulations.get(serial) if is_simulation(serial) else self.registry.get(serial) if serial else None

    def _transport(self, serial):
        return SimulationTransport(self.simulations.client(serial)) if is_simulation(serial) else self.adb

    def capture_device(self, serial):
        return self._transport(serial).frame() if is_simulation(serial) else self.capture.capture(serial)

    def _device_available(self, serial):
        device = self._device_record(serial)
        return bool(device and device.available)

    def _selection_changed(self, current, previous):
        # A real row selection is an explicit return to the physical transport.
        if current is not None:
            self.active_simulation = None
        self.preview.clear()
        self._refresh_device_details()
        self.device_manager.set_available(bool(self.selected_serial()), self.busy(self.selected_serial()))
        self._show_execution_line()
        serial = self.selected_serial()
        if is_simulation(serial):
            self.live_panel.status.setText(SIMULATION_LABEL)
            self.update_simulations()
            return
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
                    self._screen_info[serial] = info
                    self._refresh_device_details()
                    orientation = f"{info.orientation}°" if info.orientation is not None else "unavailable"
                    self.live_panel.geometry_label.setText(f"Android {info.width} × {info.height} · rotation {orientation}")
            self._submit(lambda: self.adb.screen_info(serial), metadata)
            if hasattr(self.adb, "android_version"):
                def version_done(version, error):
                    if not token.is_set() and serial == self.selected_serial() and not error:
                        self._android_versions[serial] = version
                        self._refresh_device_details()
                self._submit(lambda: self.adb.android_version(serial), version_done)
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
        self._submit(lambda: self.capture_device(serial), finished)

    def _control(self, serial, operation, *, recorded=None, duration=0):
        if self._emergency_latched:
            self.log("Emergency stop is latched. Reset it before sending device input.")
            return
        if not serial or not self._device_available(serial) or self.busy(serial) or self._closing:
            self.log("Select an available, idle phone. Manual control is blocked while its worker runs.")
            return
        self.pending_controls.add(serial)
        self._sync_controls()
        cancelled = self._manual_cancel
        connection = self._connection_token(serial)
        generation = self._device_record(serial).generation
        ticket = self.recorder.ticket(serial, generation, recorded, duration) if recorded else None
        capture_evidence = bool(ticket and recorded and recorded.startswith("tap(") and self.recorder_panel.capture_evidence.isChecked())
        def dispatch():
            current = self._device_record(serial)
            if cancelled.is_set() or connection.is_set() or not current or not current.available or current.generation != generation:
                raise RuntimeError("Control command cancelled by emergency stop or changed device connection")
            evidence=None
            if capture_evidence:
                try:
                    snapshot=self.capture_device(serial)
                    evidence=ScreenshotEvidence(serial,snapshot.png,(snapshot.width,snapshot.height))
                except Exception:
                    # Input remains usable; conversion clearly reports missing evidence.
                    evidence=None
                current=self._device_record(serial)
                if cancelled.is_set() or connection.is_set() or not current or not current.available or current.generation!=generation:
                    raise RuntimeError("Control cancelled while capturing step evidence")
            started = time.monotonic()
            operation()
            return (started,evidence) if ticket else started
        def finished(result, error):
            self.pending_controls.discard(serial)
            # ADB acknowledgment does not prove application-level success; a
            # changed connection invalidates the recording completion as well.
            current = self._device_record(serial)
            failure = error or ("Device connection changed" if connection.is_set() or not current or current.generation != generation else None)
            started,evidence = result if ticket and result is not None else (result,None)
            self.recorder.complete(ticket, started, failure, evidence=evidence)
            self.recorder_panel.refresh()
            self.log(failure or f"Control command completed on {serial}")
            self._sync_controls()
        self._submit(dispatch, finished)

    def _key(self, key):
        serial = self.selected_serial()
        code = {"HOME": "home()", "BACK": "back()"}.get(key)
        self._control(serial, lambda: self._transport(serial).key(serial, key), recorded=code)

    def _gesture(self, start, end, milliseconds):
        serial = self.selected_serial()
        self._gesture_on(serial, self.preview, start, end, milliseconds)

    def _gesture_on(self, serial, preview, start, end, milliseconds):
        frame = preview.frame
        if not frame or frame.serial != serial or time.monotonic() - frame.captured_at > 3:
            self.log("Preview is stale. Capture a fresh frame before sending input.")
            return
        if start == end and milliseconds < 500:
            self._control(serial, lambda: self._transport(serial).tap(serial, *start), recorded=f"tap({start[0]}, {start[1]})")
        else:
            seconds = milliseconds / 1000
            code = (f"longPress(Location({start[0]}, {start[1]}), duration={seconds})" if start == end
                    else f"swipe({start[0]}, {start[1]}, {end[0]}, {end[1]}, duration={seconds})")
            self._control(serial, lambda: self._transport(serial).swipe(serial, *start, *end, duration_ms=milliseconds),
                          recorded=code, duration=seconds)

    def _double_tap(self, serial, preview, x, y):
        frame = preview.frame
        if not frame or frame.serial != serial or time.monotonic() - frame.captured_at > 3:
            self.log("Preview is stale. Wait for a fresh frame before double tapping.")
            return
        cancelled = self._manual_cancel
        connection = self._connection_token(serial)
        def operation():
            self._transport(serial).tap(serial, x, y)
            if cancelled.wait(0.12) or connection.is_set() or not self._device_available(serial):
                raise RuntimeError("Second tap cancelled")
            self._transport(serial).tap(serial, x, y)
        self._control(serial, operation, recorded=f"doubleClick(Location({x}, {y}), interval=0.12)", duration=.12)

    def start_live(self, checked=False, *, serial=None):
        serial = serial or self.selected_serial()
        if is_simulation(serial):
            self._preview_modes[serial] = "simulation"
            self.update_simulations()
            return
        if self._closing or not self._device_available(serial):
            self.log("Select an authorized connected phone to start video.")
            return
        try:
            self.streams.start(serial, self.live_panel.options())
            self._preview_modes[serial] = "live"
            self._stream_sequences.pop(serial, None)
            # The approved layout has one viewer. Do not allocate or repaint a
            # second hidden PhonePreview for the same selected stream.
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
        if is_simulation(serial):
            self._preview_modes[serial] = "stopped"
            self.preview.clear()
            return
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
        if is_simulation(serial):
            self.start_live(serial=serial)
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
                self.live_panel.status.setText(text if serial == selected else self.live_panel.status.text())
                if self.event_log:
                    self.event_log.info("Video state changed: %s: %s", state.state, state.error or "")
                self._stream_states[serial] = text
                if state.state in ("failed", "stopped") and self._preview_modes.get(serial) == "live":
                    if serial in self.live_panel.tiles:
                        self.live_panel.tiles[serial][1].clear()
                    if serial == selected:
                        self.preview.clear()
            frame = self.streams.latest(serial)
            if frame is None or not self._device_available(serial) or self._preview_modes.get(serial) != "live":
                continue
            if serial == selected and self.preview.isVisible() and self.preview.frame is not frame:
                try:
                    self.preview.set_video_frame(frame)
                    self._stream_sequences[serial] = frame.sequence
                    info = ScreenInfo(frame.source_width, frame.source_height, frame.orientation) if frame.source_width and frame.source_height else None
                    if info is not None and self._screen_info.get(serial) != info:
                        self._screen_info[serial] = info
                        self._refresh_device_details()
                    self.live_panel.geometry_label.setText(
                        f"Android {frame.source_width} × {frame.source_height} · encoded {frame.width} × {frame.height}"
                        f" · rotation {str(frame.orientation) + '°' if frame.orientation is not None else 'unavailable'}")
                except ValueError as error:
                    self.streams.stop(serial)
                    self.preview.clear()
                    self.log(str(error))

    def capture_region(self, *, template_reference=None, match_options=None):
        serial = self.selected_serial()
        if not serial or self._closing:
            self.log("Select an authorized phone before capturing an image region.")
            return
        token = self._connection_token(serial)
        script = self.path
        root = self.project_root
        def current_image():
            if token.is_set() or not self._device_available(serial):
                raise RuntimeError("Device connection changed. Reconnect and capture again.")
            captured = self.capture_device(serial)
            if token.is_set():
                raise RuntimeError("Device disconnected during capture")
            image = QImage.fromData(captured.png, "PNG")
            if image.isNull():
                raise ValueError("Device screenshot could not be decoded")
            return image

        def operation():
            template = load_asset(root, template_reference) if template_reference else None
            return current_image(), template

        def open_dialog(result, error):
            if token.is_set():
                return
            if error:
                self.log(error)
                return
            if root != self.project_root or script != self.path:
                self.log("Capture cancelled because the active project or script changed. Capture again.")
                return
            image, template = result
            try:
                # AssetLibrary checks canonical containment, including symlinks.
                from app.projects.library import AssetLibrary
                image_root = AssetLibrary(root).image_root
                image_root.mkdir(exist_ok=True)
            except (OSError, ValueError) as exception:
                self.log(str(exception))
                return
            dialog = CaptureDialog(image, serial, parent=self, test_frame_provider=current_image,
                                   script_directory=script.parent if script else None,
                                   save_directory=image_root, template_image=template)
            dialog.preprocessing.setCurrentText(self.visual_tools.preprocess.currentText())
            if match_options is not None:
                threshold, scales, offset, region = match_options
                dialog.threshold.setValue(threshold)
                dialog.scales.setText(", ".join(map(str, scales)))
                if region is not None:
                    try:
                        dialog.select_region(region)
                    except ValueError as exception:
                        self.log(str(exception))
                        dialog.deleteLater()
                        return
                    dialog.search_selection.setChecked(True)
            self._capture_dialogs.add(dialog)
            dialog.reference_ready.connect(lambda code: self._insert_asset_reference(code, script))
            dialog.command_ready.connect(lambda code: self._insert_capture_command(code, script, root))
            dialog.asset_saved.connect(lambda path, region: self._asset_saved(path, region))
            def finished(result):
                self._capture_dialogs.discard(dialog)
                dialog.deleteLater()
            dialog.finished.connect(finished)
            dialog.show()
        # A full-resolution ADB freeze avoids saving scaled video templates;
        # live rendering continues independently while selection is open.
        self._submit(operation, open_dialog)

    def get_coordinate(self):
        serial = self.selected_serial()
        if not serial or self._closing:
            self.log("Select an authorized phone before picking a coordinate.")
            return
        token = self._connection_token(serial)
        script = self.path
        def operation():
            if token.is_set() or not self._device_available(serial):
                raise RuntimeError("Device connection changed. Reconnect and try again.")
            captured = self.capture_device(serial)
            if token.is_set():
                raise RuntimeError("Device disconnected during coordinate capture")
            image = QImage.fromData(captured.png, "PNG")
            if image.isNull():
                raise ValueError("Device screenshot could not be decoded")
            return image
        def opened(image, error):
            if error:
                self.log(error)
                return
            if token.is_set() or self._closing or serial != self.selected_serial():
                return
            self.show_workspace("studio")
            self.shell.close_coordinate_inspector()
            inspector = CoordinateInspector(image, serial)
            def insert(code):
                if script == self.path and self.editor.is_ready:
                    self.insert_code(code)
                    self.shell.close_coordinate_inspector()
                else:
                    self.log("Editor document changed; pick the coordinate again before inserting.")
            inspector.insert_requested.connect(insert)
            inspector.exit_requested.connect(self.shell.close_coordinate_inspector)
            self.shell.show_coordinate_inspector(inspector)
        self._submit(operation, opened)

    def _asset_saved(self, path, region):
        self.log(f"Saved {path} · Android {region}")
        self.refresh_assets()
        if self.editor.is_ready:
            self.editor.set_project_root(self.project_root, script_dir=self.path.parent if self.path else None)

    def _insert_capture_command(self, code, script, root):
        if self.path != script or self.project_root != root or not self.editor.is_ready:
            self.log(f"Image saved; editor document changed. Copy command manually: {code.strip()}")
            return
        self.editor.insert(code)

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
        self.project_label.setText(f"Project: {root.name}")
        self.project_label.setToolTip(str(root))
        if hasattr(self, "shell"):
            self.shell.project.refresh()
            self.project_panel.set_project(root)
        self.refresh_assets()
        self.log(f"Image library: {root / 'images'} · project: {root}")

    def choose_project(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose project image library root", str(self.project_root))
        if directory:
            try:
                self._set_project(directory)
            except (OSError, ValueError) as error:
                self.log(str(error))

    def save_capture(self):
        serial = self.selected_serial()
        if not serial or self._closing:
            self.log("Select an authorized phone before saving a full-resolution screenshot.")
            return
        token = self._connection_token(serial)
        path, _ = QFileDialog.getSaveFileName(self, "Save full-resolution device screenshot", str(self.project_root / "capture.png"), "PNG (*.png)")
        if path:
            def operation():
                if token.is_set():
                    raise RuntimeError("Capture cancelled: device connection changed")
                frame = self.capture_device(serial)
                if token.is_set():
                    raise RuntimeError("Device disconnected during capture; screenshot was not saved")
                self._atomic_write(Path(path), frame.png)
                return f"Saved full-resolution screenshot from {serial}: {path}"
            self._submit(operation, lambda result, error: self.log(error or result))

    def _confirm_discard(self):
        if self.editor.source == self.saved_source:
            return True
        answer = QMessageBox.question(self, "Unsaved changes", "Save changes to the current script?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return self.save_script() if answer == QMessageBox.StandardButton.Save else answer == QMessageBox.StandardButton.Discard

    def _confirm_all_documents(self):
        self.shell.documents.remember()
        for index, document in enumerate(self.shell.documents.documents):
            if document.source != document.saved:
                self.shell.documents.bar.setCurrentIndex(index)
                if self.shell.documents.current != index or not self._confirm_discard():
                    return False
        return True

    def open_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Python script", "", "Python (*.py)")
        if path:
            self.open_script_path(Path(path))

    def open_script_path(self, path):
        from app.projects.library import AssetLibrary
        try:
            candidate = Path(path).resolve()
            for index, document in enumerate(self.shell.documents.documents):
                if document.path and document.path.resolve() == candidate:
                    self.shell.documents.bar.setCurrentIndex(index)
                    self.show_workspace("studio")
                    return
            if candidate.stat().st_size > 1_000_000:
                raise ValueError("Script exceeds 1 MB limit")
            source = candidate.read_text(encoding="utf-8")
            root = self.project_root if self._project_explicit and candidate.is_relative_to(self.project_root) else discover_project(candidate)
            AssetLibrary(root, candidate.parent)
            self.shell.documents.add(candidate, source, root)
            self.show_workspace("studio")
        except (OSError, ValueError) as error:
            self.notify(f"Could not open script: {error}")

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
            if hasattr(self.editor, "set_document_path"):
                self.editor.set_document_path(path.resolve(), self.project_root)
                self.editor.persist_current_breakpoints()
            self._update_title()
            return True
        except (OSError, ValueError) as error:
            self.log(str(error))
            return False

    def _update_title(self):
        dirty = " *" if self.editor.source != self.saved_source else ""
        self.setWindowTitle(f"{self.path.name if self.path else 'Untitled.py'}{dirty} · Android Automation Studio · Script Studio")
        self._show_execution_line()
        if hasattr(self, "shell"):
            self.shell.documents.remember()

    def run_script(self):
        serial = self.selected_serial()
        self._approve_and_run([(serial, self.editor.source, str(self.path or "<editor>"), self.project_root)])

    def debug_script(self):
        self.show_workspace("debugger")
        self._approve_and_run([(self.selected_serial(), self.editor.source,
                                str(self.path or "<editor>"), self.project_root)], debug=True)

    def _project_search_result(self, path, line):
        self.open_script_path(Path(path))
        self.show_workspace("studio")
        self.editor.reveal_line(line)

    def _debug_command(self, run_id, command, payload):
        try:
            self.runtime.debug_command(run_id, command, **payload)
        except Exception as error:
            self.debugger_panel.command_failed(run_id, str(error))

    def _debug_source(self, path, line, source_hash):
        import hashlib
        document = self._run_documents.get(self.debugger_panel.selected_run())
        approved = document.get("debug_sources", {}).get(path) if document else None
        if approved is None or hashlib.sha256(approved.encode()).hexdigest() != source_hash:
            self.notify("This frame has no approved project source snapshot.")
            return
        if path != str(self.path or "<editor>"):
            try:
                target = Path(path).resolve(strict=True)
                if not target.is_relative_to(Path(document["project_root"]).resolve()) or target.read_text(encoding="utf-8") != approved:
                    raise ValueError("Source on disk differs from the running snapshot")
                existing = next((d for d in self.shell.documents.documents if d.path and d.path.resolve() == target), None)
                if existing and existing.source != approved:
                    raise ValueError("An edited source tab differs from the running snapshot")
                self.open_script_path(target)
                self.show_workspace("debugger")
            except (OSError, ValueError) as error:
                self.notify(f"Current edits preserved: {error}")
                return
        if self.editor.source != approved:
            self.notify("Current edits differ from the approved source; navigation was refused.")
            return
        self.editor.reveal_line(line)

    def _set_debug_breakpoints(self, lines):
        self.editor.set_breakpoints(lines)
        if not self.editor.is_ready:
            self._debug_breakpoints(lines)

    def _debug_breakpoints(self, lines):
        self.debugger_panel.set_breakpoints(lines, getattr(self.editor, "_document_key", None))
        # Breakpoint edits affect only the exact currently executed snapshot.
        for run in self.run_states:
            document = self._run_documents.get(run.run_id)
            path = str(self.path or "<editor>")
            approved = document.get("debug_sources", {}).get(path) if document else None
            if (run.exitcode is None and run.run_id in self.debugger_panel.sessions and document
                    and approved == self.editor.source
                    and (path != "<editor>" or document.get("document_key") == getattr(self.editor, "_document_key", None))):
                self._debug_command(run.run_id, "set_breakpoints", {"lines": list(lines), "source_path": path})

    def _task_source(self):
        serial = self.selected_serial()
        if not serial or not self._device_available(serial):
            raise ValueError("Select an available device before creating a task")
        return {"source": self.editor.source, "serial": serial,
                "script_id": str(self.path or "<editor>"), "project_root": str(self.project_root)}

    def _task_groups(self):
        groups = {}
        for serial, data in self.device_manager.labels.items():
            if name := data.get("group", "").strip():
                groups.setdefault(name, []).append(serial)
        simulations = [info.serial for info in self.simulations.snapshot() if info.available]
        if simulations:
            groups["Current simulated devices"] = simulations
        return groups

    def _authorize_task(self, task, confirm):
        serial = task.serial
        token = self._connection_token(serial)
        if self._closing or self._emergency_latched or not self._device_available(serial) or token.is_set():
            self.notify("Select an available task device and reset emergency stop before approving.")
            return False
        if not confirm():
            return False
        if (self._closing or self._emergency_latched or not self._device_available(serial)
                or token.is_set() or self._connection_token(serial) is not token):
            self.notify("The device connection changed during approval. Review and approve the task again.")
            return False
        self.runtime.allow_device(serial)
        self._task_connections[task.task_id] = token
        return True

    def _dispatch_task(self, task):
        serial = task.serial
        token = self._task_connections.get(task.task_id)
        if (token is None or token.is_set() or self._connection_token(serial) is not token
                or self._closing or self._emergency_latched or self.busy(serial)
                or not self._device_available(serial)):
            raise RuntimeError("Task authorization is obsolete or the device is busy/unavailable")
        if self.recorder.serial == serial and self.recorder.state != "stopped":
            self.stop_recording("Scheduled script started; studio controls are blocked")
        if self.preview.frame and self.preview.frame.serial == serial:
            self.preview.cancel_input()
        if serial in self.live_panel.tiles:
            self.live_panel.tiles[serial][1].cancel_input()
        simulation = is_simulation(serial)
        options = {"simulation_config": self.simulations.config(serial)} if simulation else {}
        if executable := self.settings.value("ocr_executable", ""):
            options["ocr_config"] = {"executable": executable}
        request_id = self.runtime.start(task.source, serial, trusted=True,
            backend="simulation" if simulation else "adb", adb_executable=self.adb.executable,
            script_id=task.script_id, project_root=task.project_root, **options)
        self.pending_runs[request_id] = serial
        self._request_documents[request_id] = {"source": task.source, "script_id": task.script_id,
            "project_root": task.project_root,
            "document_key": self._matching_document(task.source, task.script_id, task.project_root)}
        return request_id

    def _matching_document(self, source, script_id, root):
        if (source == self.editor.source and script_id == str(self.path or "<editor>")
                and Path(root).resolve() == self.project_root):
            return getattr(self.editor, "_document_key", None)
        return None

    def _scheduler_tick(self):
        if self._closing:
            return
        try:
            self.scheduler.tick()
        except Exception as error:
            self.scheduler.pause()
            self.notify(f"Scheduling paused after a persistence/dispatch error: {error}")

    def _revoke_scheduled_device(self, serial):
        if getattr(self, "task_store", None) is not None:
            self.scheduler.revoke_device(serial)
            for task in self.task_store.tasks():
                if task.serial == serial:
                    self._task_connections.pop(task.task_id, None)

    def _selected_phones(self):
        if self.active_simulation:
            return [self.selected_serial()] if self.selected_serial() else []
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
            if not is_simulation(serial):
                self.devices.currentItem().setToolTip(f"Assigned script: {path}")
            self._refresh_device_details()

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

    def _approve_and_run(self, requests, *, debug=False):
        if not self.editor.is_ready or not requests or self._closing or self._emergency_latched:
            self.log("Wait for the editor and select available phones; reset emergency stop before running.")
            return
        debug_lines = list(self.editor.breakpoints) if debug else []
        try:
            connections = {}
            document_keys = {}
            debug_sources, file_breakpoints = {}, {}
            for serial, source, script_id, root in requests:
                if not serial or not self._device_available(serial) or self.busy(serial):
                    raise ValueError(f"Select an idle authorized phone: {serial or 'none'}")
                if script_id != "<editor>" and not Path(script_id).resolve().is_relative_to(Path(root).resolve()):
                    raise ValueError("Open or save the script inside the active project before running")
                compile(source, script_id, "exec")
                connections[serial] = self._connection_token(serial)
                document_keys[serial] = self._matching_document(source, script_id, root)
                if debug:
                    from app.automation.debug_sources import snapshot_sources
                    snapshots = snapshot_sources(root, script_id, source)
                    debug_sources[serial] = snapshots
                    file_breakpoints[serial] = {}
                    for path, captured in snapshots.items():
                        if path == script_id:
                            continue
                        persisted = self.editor.breakpoint_store.load(path, root, captured)
                        if persisted:
                            file_breakpoints[serial][path] = persisted
        except (OSError, ValueError, SyntaxError, RuntimeError) as error:
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
                if (self.busy(serial) or not self._device_available(serial) or self._closing or self._emergency_latched
                        or connections[serial].is_set() or self._connection_token(serial) is not connections[serial]):
                    raise RuntimeError(f"Phone {serial} became unavailable or busy; no run queued")
                self.runtime.allow_device(serial)
                if self.recorder.serial == serial and self.recorder.state != "stopped":
                    self.stop_recording("Script execution started; studio controls are blocked for this phone")
                if self.preview.frame and self.preview.frame.serial == serial:
                    self.preview.cancel_input()
                if serial in self.live_panel.tiles:
                    self.live_panel.tiles[serial][1].cancel_input()
                simulation = is_simulation(serial)
                options = {"simulation_config": self.simulations.config(serial)} if simulation else {}
                if debug:
                    options.update(debug=True, breakpoints=debug_lines, debug_sources=debug_sources[serial],
                                   file_breakpoints=file_breakpoints[serial])
                if configured_ocr := self.settings.value("ocr_executable", ""):
                    options["ocr_config"] = {"executable": configured_ocr}
                request_id = self.runtime.start(source, serial, trusted=True, backend="simulation" if simulation else "adb",
                    adb_executable=self.adb.executable, script_id=script_id, project_root=str(root), **options)
                self.pending_runs[request_id] = serial
                self._request_documents[request_id] = {"source": source, "script_id": script_id,
                    "project_root": str(root), "document_key": document_keys[serial],
                    "debug_sources": debug_sources.get(serial, {})}
                self.log(f"Queued run request {request_id} on {serial}")
            except Exception as error:
                self.log(str(error))

    def _active_run_id(self):
        if hasattr(self, "shell") and self.shell.current == "debugger":
            selected = self.debugger_panel.selected_run()
            if selected:
                return selected
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

    def toggle_run_pause(self):
        self._control_run("resume" if self.actions["resume"].isEnabled() else "pause")

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
        approved = document.get("debug_sources", {}).get(expected_path) if document else None
        matches = bool(document and (
            approved == self.editor.source if approved is not None else document["source"] == self.editor.source
                and document["script_id"] == expected_path))
        if (matches and location
                and (expected_path != "<editor>" or document.get("document_key") == getattr(self.editor, "_document_key", None))
                and location[0] == expected_path
                and run and run.exitcode is None):
            self.editor.set_execution_line(location[1])
        else:
            self.editor.set_execution_line(None)

    def _runtime_event(self, event):
        if self._shutdown_complete:
            return
        self.scheduler.handle_event(event)
        self.debugger_panel.on_event(event)
        if event.get("event") == "error":
            if self.event_log:
                self.event_log.warning("Script worker error; inspect execution panel")
            self._persist_failure(event)
        elif event.get("event") == "debug_error" and self.event_log:
            self.event_log.warning("Debugger command failed; inspect debugger panel")
        if event.get("event") == "debug_stopped":
            self._run_lines[event["run_id"]] = (event["source_path"], event["line"])
            self._show_execution_line()
            self.log(f"Debugger stopped: {event.get('reason')} at {event['source_path']}:{event['line']}")
            return  # Variable values belong only in the debugger inspector.
        self.execution_panel.on_event(event)
        if event.get("event") == "line":
            self._run_lines[event["run_id"]] = (event["source_path"], event["line"])
            self._show_execution_line()
            return
        if event.get("event") == "request_error":
            if event.get("command") == "debug_command":
                self.debugger_panel.command_failed(event.get("run_id"), event.get("message", "Debug command failed"))
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
        # Keep structured events in ExecutionPanel and the application log.
        # The default console is exclusively readable script output.
        kind = event.get("event")
        if kind == "request" and event.get("command") == "start":
            self.logs.appendPlainText("Script started")
        elif kind == "output":
            self.logs.appendPlainText(str(event.get("text", "")).rstrip("\n"))
        elif kind == "error":
            location = ""
            if event.get("source_line"):
                location = f" ({Path(event.get('source_path') or '<editor>').name}:{event['source_line']})"
            self.logs.appendPlainText(f"{event.get('error_type', 'Error')}: {event.get('message', '')}{location}")
        elif kind == "status" and event.get("state") in ("completed", "cancelled", "failed"):
            self.logs.appendPlainText("Script " + event["state"])
        elif kind == "request_error" and event.get("command") == "start":
            self.logs.appendPlainText("Could not start script: " + str(event.get("message", "Unknown error")))

    def inspect_run_failure(self, run_id):
        event = self.execution_panel.failures.get(run_id)
        document = self._run_documents.get(run_id)
        if not event or not document:
            self.notify("No source-linked failure is available for this run."); return
        line = event.get("source_line")
        if (type(line) is not int or line < 1 or event.get("source_path") != document["script_id"]
                or str(self.path or "<editor>") != document["script_id"] or self.editor.source != document["source"]):
            self.notify("Failure refers to another file or an older source snapshot. Open the matching unedited script and inspect the traceback; your current edits were preserved."); return
        self.show_workspace("studio")
        self.editor.reveal_line(line)
        self.notify(self.execution_panel.failure_detail(event))

    def _persist_failure(self, event):
        if self.recovery_journal is None:
            return
        serial = event.get("serial")
        token = self._connection_token(serial)
        capture = bool(getattr(self.recovery_panel, "capture_failures", None)
                       and self.recovery_panel.capture_failures.isChecked())
        def same_failure_context():
            return (not token.is_set() and self._connection_token(serial) is token
                    and serial not in self.pending_runs.values()
                    and not any(run.serial == serial and run.run_id != event.get("run_id")
                                and run.exitcode is None for run in self.run_states))
        def operation():
            evidence = None
            if capture and same_failure_context() and self._device_available(serial):
                try:
                    frame = self.capture_device(serial)
                    if same_failure_context() and frame.serial == serial:
                        evidence = ScreenshotEvidence(serial=serial, png=frame.png, size=(frame.width, frame.height))
                except Exception:
                    pass  # Preserve the failure even when capture is unavailable.
            return self.recovery_journal.record_event(event, evidence)
        def finished(record_id, error):
            if error:
                self.log(f"Failure history could not be saved: {error}")
            else:
                try:
                    self.recovery_panel.refresh()
                except Exception as refresh_error:
                    self.log(f"Failure history could not be read: {refresh_error}")
        self._submit(operation, finished)

    def _runtime_snapshot(self, states):
        if self._shutdown_complete:
            return
        self.run_states = list(states)
        self.scheduler.set_busy_serials(self.run_states)
        self.debugger_panel.update_runs(self.run_states)
        self.execution_panel.update_runs(self.run_states)
        self._release_confirmed_runs()
        self._show_execution_line()
        self._sync_controls()

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
        self.scheduler.emergency_stop()
        self._task_connections.clear()
        if self.recorder.state != "stopped":
            self.stop_recording("Emergency stop")
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
        if not self._closing and not self._confirm_all_documents():
            event.ignore()
            return
        self._closing = True
        self.scheduler.pause()
        self.task_timer.stop()
        if hasattr(self.task_panel, "timer"):
            self.task_panel.timer.stop()
        self._diagnostic_cancel.set()
        if self.recorder.state != "stopped":
            self.stop_recording("Window closing")
        self._manual_cancel.set()
        self.run_action.setEnabled(False)
        self.preview_timer.stop()
        self.stream_timer.stop()
        self.discovery_timer.stop()
        for dialog in tuple(self._capture_dialogs):
            dialog.reject()
        self.settings.setValue("geometry", self.saveGeometry())
        self.shell.save()
        self.control_timer.stop()
        self.metrics_timer.stop()
        self.simulation_timer.stop()
        self.settings.sync()
        runtime_closed = self.runtime.close(timeout=0)
        streams_closed = self.streams.close(timeout=0)
        if not runtime_closed or not streams_closed or not self.pool.waitForDone(0) or self._capture_dialogs:
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        self.simulations.close()
        if self.draft_recovery is not None:
            try:
                self.draft_recovery.stop(clean=True)
            except (OSError, ValueError) as error:
                self.log(f"Draft recovery cleanup failed; stored files preserved: {error}")
        if self._connection_wizard is not None:
            self._connection_wizard.close()
        if self.task_store is not None:
            self.task_store.close()
        self.editor.shutdown()
        self._shutdown_complete = True
        event.accept()
