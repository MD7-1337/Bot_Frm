"""Editable Python timeline. Insertion never dispatches commands or starts replay."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QLabel, QPushButton,
                              QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


class RecorderPanel(QWidget):
    start_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    insert_requested = Signal()

    def __init__(self, recorder, parent=None):
        super().__init__(parent)
        self.recorder = recorder
        self._rendered_count = 0
        layout = QVBoxLayout(self)
        hint = QLabel("Record controls sent through studio previews and Home/Back. Edit generated calls below; replay uses normal trusted script execution.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        controls = QGridLayout()
        for index, (label, callback) in enumerate((
            ("Start on current phone", self.start_requested.emit),
            ("Pause / resume recording", self.pause_requested.emit),
            ("Stop recording", self.stop_requested.emit),
            ("Insert Python into Monaco", self.insert_requested.emit),
            ("Delete step", self.delete_step), ("Move up", lambda: self.move_step(-1)),
            ("Move down", lambda: self.move_step(1)),
        )):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, target=callback: target())
            controls.addWidget(button, index // 4, index % 4)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Editable Python action / delay"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAccessibleName("Recorded Python action timeline")
        self.table.setMinimumHeight(70)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self, *, reset=False):
        if reset:
            self.table.setRowCount(0)
            self._rendered_count = 0
        for code in self.recorder.actions[self._rendered_count:]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(code))
        self._rendered_count = len(self.recorder.actions)
        self.status.setText(f"{self.recorder.state} · {self.recorder.serial or 'no phone'}\n{self.recorder.reason}")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers if self.recorder.state == "stopped"
                                   else QAbstractItemView.EditTrigger.NoEditTriggers)

    def delete_step(self):
        if self.recorder.state == "stopped" and self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def move_step(self, delta):
        row = self.table.currentRow()
        other = row + delta
        if self.recorder.state != "stopped" or row < 0 or not 0 <= other < self.table.rowCount():
            return
        a, b = self.table.item(row, 0).text(), self.table.item(other, 0).text()
        self.table.item(row, 0).setText(b)
        self.table.item(other, 0).setText(a)
        self.table.selectRow(other)

    def source(self):
        if self.recorder.state != "stopped":
            raise ValueError("Stop recording before editing or inserting its timeline")
        actions = [self.recorder.validate_action(self.table.item(row, 0).text())
                   for row in range(self.table.rowCount())]
        self.recorder.actions = actions
        self._rendered_count = len(actions)
        return self.recorder.source()
