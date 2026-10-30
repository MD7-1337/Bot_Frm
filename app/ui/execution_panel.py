"""Per-run status presentation, separate from worker control and source editing."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QTableWidget,
                              QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)


class ExecutionPanel(QWidget):
    run_selected = Signal(str)
    failure_selected = Signal(str)

    def __init__(self, logs, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel("No script runs. Select a phone and approve a trusted script to begin.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        tabs = QTabWidget()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Phone", "Script", "State", "Line", "Error"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda item: self.failure_selected.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.table.setAccessibleName("Independent script executions")
        tabs.addTab(self.table, "Script runs")
        tabs.addTab(logs, "Output and events")
        layout.addWidget(tabs)
        self.rows: dict[str, int] = {}
        self.lines: dict[str, int] = {}
        self.errors: dict[str, str] = {}
        self.failures: dict[str, dict] = {}

    def selected_run(self) -> str | None:
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _selection_changed(self):
        run_id = self.selected_run()
        if run_id:
            self.run_selected.emit(run_id)

    def update_runs(self, runs):
        selected = self.selected_run()
        blocker = QSignalBlocker(self.table)
        active = 0
        for run in runs[-100:]:
            active += int(run.exitcode is None)
            if run.run_id not in self.rows:
                if self.table.rowCount() >= 100:
                    removed = [key for key, row in self.rows.items() if row == 0]
                    self.table.removeRow(0)
                    self.rows = {key: row - 1 for key, row in self.rows.items() if row > 0}
                    for key in removed:
                        self.lines.pop(key, None)
                        self.errors.pop(key, None)
                        self.failures.pop(key, None)
                self.rows[run.run_id] = self.table.rowCount()
                self.table.insertRow(self.table.rowCount())
            row = self.rows[run.run_id]
            values = [run.serial, Path(run.script_id).name, run.state,
                      str(self.lines.get(run.run_id, "")), self.errors.get(run.run_id, "")]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, run.run_id)
                if column == 1:
                    item.setToolTip(run.script_id)
                elif column == 4 and run.run_id in self.failures:
                    item.setToolTip(self.failure_detail(self.failures[run.run_id]))
                self.table.setItem(row, column, item)
        if selected in self.rows:
            self.table.selectRow(self.rows[selected])
        del blocker
        self.summary.setText(f"{active} active run(s). Select a row for Pause, Resume or Stop. Last 100 runs shown.")

    def on_event(self, event):
        run_id = event.get("run_id")
        kind = event.get("event")
        if kind == "line":
            self.lines[run_id] = event["line"]
        elif kind == "error":
            self.failures[run_id] = event
            self.errors[run_id] = f"{event.get('error_type', 'Error')}: {event.get('message', '')}"
        if run_id in self.rows:
            row = self.rows[run_id]
            if kind == "line":
                item = QTableWidgetItem(str(event["line"]))
                item.setData(Qt.ItemDataRole.UserRole, run_id)
                self.table.setItem(row, 3, item)
            elif kind == "error":
                item = QTableWidgetItem(self.errors[run_id])
                item.setData(Qt.ItemDataRole.UserRole, run_id)
                item.setToolTip(self.failure_detail(event))
                self.table.setItem(row, 4, item)

    @staticmethod
    def failure_detail(event):
        failure = event.get("failure", {})
        return (f"{failure.get('category', 'unclassified')}: {failure.get('advice', '')}\n"
                f"{event.get('source_path', '')}:{event.get('source_line', '')}\n"
                "Double-click to inspect the failed line. Restart is explicit; no automatic retry.\n"
                + event.get("traceback", ""))
