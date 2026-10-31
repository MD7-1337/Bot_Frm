"""Native debugger controls; frames and variables never cross the web bridge."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget,
                              QListWidgetItem, QPlainTextEdit, QPushButton,
                              QTabWidget, QTreeWidget, QTreeWidgetItem,
                              QVBoxLayout, QWidget)


class DebuggerPanel(QWidget):
    start_requested = Signal()
    command_requested = Signal(str, str, dict)
    stop_requested = Signal(str)
    breakpoints_changed = Signal(object)
    source_requested = Signal(str, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.summary = QLabel("Set a gutter breakpoint in Monaco, then Debug trusted script.")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        toolbar = QHBoxLayout()
        self.start_button = QPushButton("Debug trusted script…")
        self.start_button.clicked.connect(self.start_requested)
        toolbar.addWidget(self.start_button)
        self.runs = QComboBox()
        self.runs.setAccessibleName("Debug device and run")
        self.runs.currentIndexChanged.connect(self._render)
        toolbar.addWidget(self.runs, 1)
        layout.addLayout(toolbar)
        controls = QHBoxLayout()
        self.buttons = {}
        for command, title in (("continue", "Continue"), ("pause", "Pause"),
                               ("step_over", "Step over"), ("step_into", "Step into"),
                               ("step_out", "Step out"), ("stop", "Stop")):
            button = QPushButton(title)
            button.setAccessibleName("Debugger " + title)
            button.clicked.connect(lambda checked=False, action=command: self._command(action))
            controls.addWidget(button)
            self.buttons[command] = button
        layout.addLayout(controls)
        tabs = QTabWidget()
        self.variables = QTreeWidget()
        self.variables.setHeaderLabels(["Variable", "Value", "Type"])
        self.variables.setAccessibleName("Paused frame local and global variables")
        tabs.addTab(self.variables, "Variables")
        self.stack = QListWidget()
        self.stack.setAccessibleName("Debugger call stack")
        self.stack.currentRowChanged.connect(self._frame_selected)
        self.stack.itemDoubleClicked.connect(self._navigate)
        tabs.addTab(self.stack, "Call stack")
        self.breakpoints = QListWidget()
        self.breakpoints.setAccessibleName("Enabled and disabled script breakpoints")
        self.breakpoints.itemChanged.connect(self._breakpoint_checked)
        tabs.addTab(self.breakpoints, "Breakpoints")
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(1000)
        self.output.setAccessibleName("Debugger execution output and exceptions")
        tabs.addTab(self.output, "Output and exceptions")
        layout.addWidget(tabs)
        self.sessions = {}
        self._disabled = set()
        self._disabled_by_document = {}
        self._document_key = "default"
        self._render()

    def selected_run(self):
        return self.runs.currentData()

    def set_breakpoints(self, lines, document_key=None):
        """Synchronize enabled lines, retaining disabled rows per host document."""
        if document_key is not None and document_key != self._document_key:
            self._disabled_by_document[self._document_key] = set(self._disabled)
            self._document_key = document_key
            self._disabled = set(self._disabled_by_document.get(document_key, ()))
        blocker = QSignalBlocker(self.breakpoints)
        enabled = set(lines)
        self._disabled.difference_update(enabled)
        self.breakpoints.clear()
        for line in sorted(enabled | self._disabled):
            item = QListWidgetItem(f"Line {line}")
            item.setData(Qt.ItemDataRole.UserRole, line)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if line in enabled else Qt.CheckState.Unchecked)
            self.breakpoints.addItem(item)
        del blocker

    def _breakpoint_checked(self, item):
        line = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._disabled.discard(line)
        else:
            self._disabled.add(line)
        self.breakpoints_changed.emit([self.breakpoints.item(i).data(Qt.ItemDataRole.UserRole)
                                       for i in range(self.breakpoints.count())
                                       if self.breakpoints.item(i).checkState() == Qt.CheckState.Checked])

    def on_event(self, event):
        kind, run = event.get("event"), event.get("run_id")
        if kind == "debug_started":
            self.sessions[run] = {"state": "running", "pending": False, "stop": None,
                                  "source_hash": event["source_hash"]}
            self.runs.addItem(f"{event['serial']} · {Path(event['script_id']).name} · {run[:6]}", run)
            self.runs.setCurrentIndex(self.runs.count() - 1)
        session = self.sessions.get(run)
        if session is None:
            return
        if kind == "debug_stopped":
            session["stop"] = event
            session["state"] = "paused"
            if event.get("exception"):
                exception = event["exception"]
                self.output.appendPlainText(f"{exception['type']}: {exception['value']}")
        elif kind == "status":
            session["state"] = event["state"]
            if event["state"] != "paused":
                session["stop"] = None
        elif kind == "debug_ack":
            session["pending"] = False
        elif kind in {"debug_error", "error"}:
            self.output.appendPlainText(f"[{event.get('serial', '')}] {event.get('message', '')}\n{event.get('traceback', '')}")
        elif kind == "output":
            self.output.moveCursor(self.output.textCursor().MoveOperation.End)
            self.output.insertPlainText(event["text"])
        if run == self.selected_run():
            self._render()

    def update_runs(self, runs):
        for run in runs:
            if run.run_id in self.sessions:
                self.sessions[run.run_id]["state"] = run.state
        self._render()

    def _command(self, command, **payload):
        run = self.selected_run()
        session = self.sessions.get(run)
        if session is None:
            return
        if command == "stop":
            self.stop_requested.emit(run)
        elif not session["pending"]:
            session["pending"] = True
            self.command_requested.emit(run, command, payload)
            self._render()

    def command_failed(self, run, message):
        if run in self.sessions:
            self.sessions[run]["pending"] = False
        self.output.appendPlainText(message)
        self._render()

    def _frame_selected(self, index):
        if index >= 0:
            self._command("inspect", frame_index=index)

    def _navigate(self, item):
        event = self.sessions.get(self.selected_run(), {}).get("stop")
        if event:
            frame = item.data(Qt.ItemDataRole.UserRole)
            self.source_requested.emit(frame["source_path"], frame["line"], frame.get("source_hash") or "")

    def _render(self, *_):
        session = self.sessions.get(self.selected_run(), {})
        state = session.get("state", "idle")
        active = state in {"starting", "running", "paused"}
        paused = state == "paused" and session.get("stop") is not None
        pending = session.get("pending", False)
        for command, button in self.buttons.items():
            button.setEnabled(active if command == "stop" else
                              active and not pending and (state == "running" if command == "pause" else paused))
        self.summary.setText(f"Debug session: {state}. Variables are bounded previews; Python retains your OS permissions." if session
                             else "Set a gutter breakpoint in Monaco, then Debug trusted script.")
        event = session.get("stop") if paused else None
        blocker = QSignalBlocker(self.stack)
        self.stack.clear()
        self.variables.clear()
        if event:
            for scope in ("locals", "globals"):
                parent = QTreeWidgetItem([scope.title()])
                self.variables.addTopLevelItem(parent)
                for variable in event[scope]:
                    parent.addChild(QTreeWidgetItem([variable["name"], variable["value"], variable["type"]]))
                parent.setExpanded(True)
            for frame in event["stack"]:
                item = QListWidgetItem(f"{frame['name']} · {Path(frame['source_path']).name}:{frame['line']}")
                item.setData(Qt.ItemDataRole.UserRole, frame)
                self.stack.addItem(item)
            self.stack.setCurrentRow(event.get("selected_frame", 0))
        del blocker
