"""Persistent local failure evidence; never a restart/reconnect control."""
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView,
                              QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                              QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


class RecoveryPanel(QWidget):
    """Host creates with RecoveryJournal(path), feeds only worker error events."""

    def __init__(self, journal, parent=None):
        super().__init__(parent)
        self.journal = journal
        layout = QVBoxLayout(self)
        hint = QLabel("Most recent 100 local failures. Inspect the current device screen before explicitly restarting a trusted script. Input and lost transport acknowledgments are never replayed here.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.capture_failures = QCheckBox("Capture a fresh screen after failures (may contain private content)")
        self.capture_failures.setChecked(False)
        self.capture_failures.setToolTip("Optional post-failure evidence from the still-current device connection. It is captured after the failure, not at the exact failing instruction.")
        layout.addWidget(self.capture_failures)
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh history")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh)
        export = QPushButton("Export selected diagnostic…")
        export.clicked.connect(self.export_selected)
        controls.addWidget(export)
        controls.addStretch()
        layout.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["UTC time", "Device", "Failure", "Source"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAccessibleName("Persistent failure history")
        self.table.itemSelectionChanged.connect(self._show_detail)
        splitter.addWidget(self.table)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Failure traceback and recovery advice")
        self.details.document().setMaximumBlockCount(2000)
        detail_layout.addWidget(self.details)
        self.screenshot = QLabel("No failure screenshot attached")
        self.screenshot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot.setMaximumHeight(240)
        detail_layout.addWidget(self.screenshot)
        splitter.addWidget(detail)
        layout.addWidget(splitter)
        self.refresh()

    def record_event(self, event, screenshot=None):
        record_id = self.journal.record_event(event, screenshot)
        if record_id is not None:
            self.refresh()
        return record_id

    def refresh(self):
        previous = self.selected_id()
        records = self.journal.recent()
        self.table.setRowCount(0)
        selected = 0
        for row, record in enumerate(records):
            self.table.insertRow(row)
            values = (datetime.fromtimestamp(record["created"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                      record["serial"], record["error_type"],
                      f"{record['source_path']}:{record['source_line'] or '?'}")
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, record["id"])
                item.setToolTip(text)
                self.table.setItem(row, column, item)
            if record["id"] == previous:
                selected = row
        if records:
            self.table.selectRow(selected)
        else:
            self.details.setPlainText("No failures recorded. Native and simulator acceptance remain separate.")
            self.screenshot.clear()

    def selected_id(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show_detail(self):
        record_id = self.selected_id()
        record = self.journal.detail(record_id, include_screenshot=True) if record_id else None
        if not record:
            return
        self.details.setPlainText(f"{record['error_type']}: {record['message']}\n\n"
                                  f"Category: {record['category']}\n{record['advice']}\n\n"
                                  f"Run: {record['run_id']}\nDevice: {record['serial']}\n"
                                  f"Source: {record['source_path']}:{record['source_line'] or '?'}\n\n"
                                  f"{record['traceback']}")
        self.screenshot.clear()
        if record["screenshot"]:
            image = QPixmap()
            if image.loadFromData(record["screenshot"], "PNG"):
                self.screenshot.setPixmap(image.scaled(600, 220, Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation))
                self.screenshot.setToolTip("Fresh post-failure screenshot, captured after the error rather than at the exact failing instant. It may reflect later screen state and contain private content.")
        else:
            self.screenshot.setText("No failure screenshot attached. Capture manually after verifying the device state.")

    def export_selected(self):
        record_id = self.selected_id()
        if not record_id:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export local failure diagnostic (contains device/path details)",
                                            "failure-diagnostic.json", "JSON (*.json)")
        if not path:
            return
        try:
            from PySide6.QtCore import QIODevice, QSaveFile
            output = QSaveFile(path)
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            data = self.journal.export_report(record_id).encode("utf-8")
            if output.write(data) != len(data):
                output.cancelWriting()
                raise OSError(output.errorString())
            if not output.commit():
                raise OSError(output.errorString())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Diagnostic export failed", str(error))
