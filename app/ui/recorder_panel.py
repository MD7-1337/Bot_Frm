"""Editable Python timeline. Insertion never dispatches commands or starts replay."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QLabel, QPushButton,
                              QDoubleSpinBox, QHBoxLayout, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


class RecorderPanel(QWidget):
    start_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    insert_requested = Signal()
    save_requested = Signal()
    load_requested = Signal()
    replay_requested = Signal()

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
        self.buttons = {}
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
            self.buttons[label] = button
            controls.addWidget(button, index // 4, index % 4)
        layout.addLayout(controls)
        session = QHBoxLayout()
        for text, signal in (("Save session…", self.save_requested), ("Open session…", self.load_requested), ("Replay on selected phone…", self.replay_requested)):
            widget = QPushButton(text)
            widget.clicked.connect(lambda checked=False, target=signal: target.emit())
            session.addWidget(widget)
            self.buttons[text] = widget
        layout.addLayout(session)
        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Editable Python action / delay"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAccessibleName("Recorded Python action timeline")
        self.table.setMinimumHeight(70)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.table, stretch=1)
        delay = QHBoxLayout()
        delay.addWidget(QLabel("Insert delay (seconds)"))
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 86400)
        self.delay.setValue(1)
        delay.addWidget(self.delay)
        delay_button = QPushButton("Add delay")
        delay_button.clicked.connect(self.add_delay)
        delay.addWidget(delay_button)
        self.buttons["Add delay"] = delay_button
        delay.addStretch()
        layout.addLayout(delay)
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

    def set_control_state(self, can_record, state):
        self.buttons["Start on current phone"].setEnabled(can_record and state == "stopped")
        self.buttons["Pause / resume recording"].setEnabled(state in ("recording", "paused"))
        self.buttons["Stop recording"].setEnabled(state != "stopped")
        has_actions = self.table.rowCount() > 0
        for text in ("Delete step", "Move up", "Move down", "Insert Python into Monaco", "Save session…"):
            self.buttons[text].setEnabled(state == "stopped" and has_actions)
        self.buttons["Replay on selected phone…"].setEnabled(can_record and state == "stopped" and has_actions)
        self.buttons["Open session…"].setEnabled(state == "stopped")
        self.buttons["Add delay"].setEnabled(state == "stopped")

    def add_delay(self):
        if self.recorder.state != "stopped":
            return
        if self.table.rowCount() >= self.recorder.limit:
            self.status.setText("Timeline limit reached; delete a step first.")
            return
        row = self.table.currentRow() + 1 if self.table.currentRow() >= 0 else self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"sleep({self.delay.value()})"))
        self.table.selectRow(row)
