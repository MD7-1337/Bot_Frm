"""Editable Python timeline. Insertion never dispatches commands or starts replay."""
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QGridLayout, QHeaderView, QLabel, QPushButton,
                              QDoubleSpinBox, QHBoxLayout, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import ast
import math
from app.ui.design import icon


class RecorderPanel(QWidget):
    start_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    insert_requested = Signal()
    save_requested = Signal()
    load_requested = Signal()
    replay_requested = Signal()
    convert_requested = Signal()

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
        self.capture_evidence = QCheckBox("Capture pre-tap screenshots (memory-limited; included when you save a session)")
        self.capture_evidence.setChecked(True)
        layout.addWidget(self.capture_evidence)
        self.step_info = QLabel("Select a step for its action, duration, device and screenshot evidence.")
        self.step_info.setWordWrap(True)
        layout.addWidget(self.step_info)
        self.convert_button = QPushButton("Convert to Image Target…")
        self.convert_button.clicked.connect(lambda: self.convert_requested.emit())
        layout.addWidget(self.convert_button)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Editable Python action / delay", "Type", "Duration", "Device / image"])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for column in (1,2,3):
            self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._row_changed)
        self.table.itemSelectionChanged.connect(self._step_properties)
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
            item=QTableWidgetItem(code)
            item.setData(Qt.ItemDataRole.UserRole,{"evidence":self.recorder.evidence.get(row),"duration":self.recorder.durations.get(row,0.),"timestamp":self.recorder.timestamps.get(row)})
            self.table.setItem(row, 0, item)
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
        a,b=self.table.takeItem(row,0),self.table.takeItem(other,0)
        self.table.setItem(row,0,b)
        self.table.setItem(other,0,a)
        self.table.selectRow(other)

    def source(self):
        if self.recorder.state != "stopped":
            raise ValueError("Stop recording before editing or inserting its timeline")
        actions = [self.recorder.validate_action(self.table.item(row, 0).text())
                   for row in range(self.table.rowCount())]
        evidence={}
        durations={}
        timestamps={}
        for row in range(self.table.rowCount()):
            metadata=self.table.item(row,0).data(Qt.ItemDataRole.UserRole) or {}
            if metadata.get("evidence") is not None:
                evidence[row]=metadata["evidence"]
            durations[row]=metadata.get("duration",0.)
            if metadata.get("timestamp") is not None:
                timestamps[row]=metadata["timestamp"]
        self.recorder.actions,self.recorder.evidence,self.recorder.durations = actions,evidence,durations
        self.recorder.timestamps=timestamps
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
        self._step_properties()

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

    def _row_changed(self, item):
        if item.column()!=0:
            return
        code=item.text()
        metadata=item.data(Qt.ItemDataRole.UserRole) or {}
        duration=metadata.get("duration",0.)
        target=""
        try:
            call=ast.parse(code).body[0].value
            kind=call.func.id if isinstance(call.func,ast.Name) else "call"
            if kind in ("sleep","wait") and call.args and isinstance(call.args[0],ast.Constant) and type(call.args[0].value) in (int,float):
                candidate=call.args[0].value
                if 0 <= candidate <= 86400 and math.isfinite(candidate):
                    duration=candidate
                else:
                    # Preserve editable source while keeping saved metadata
                    # finite/loadable. The worker will reject invalid delays.
                    kind="invalid delay"
                    duration=0.
            if kind in ("click","find","waitImage") and call.args and isinstance(call.args[0],ast.Constant):
                target=str(call.args[0].value)
        except (SyntaxError,AttributeError,IndexError):
            kind="invalid Python"
        blocker=QSignalBlocker(self.table)
        item.setIcon(icon("visual" if target else "devices" if kind=="tap" else "recorder"))
        metadata={**metadata,"duration":duration}
        item.setData(Qt.ItemDataRole.UserRole,metadata)
        values=(kind,f"{duration:g}s" if duration else "—",target or ("SIMULATION" if str(self.recorder.serial).startswith("sim://") else self.recorder.serial or "—"))
        for column,text in enumerate(values,1):
            cell=QTableWidgetItem(text)
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            cell.setToolTip(text)
            self.table.setItem(item.row(),column,cell)
        del blocker
        self._step_properties()

    def _step_properties(self):
        row=self.table.currentRow()
        item=self.table.item(row,0) if row>=0 else None
        metadata=item.data(Qt.ItemDataRole.UserRole) or {} if item else {}
        evidence=metadata.get("evidence")
        eligible=False
        if item:
            try:
                call=ast.parse(item.text()).body[0].value
                eligible=isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=="tap"
            except (SyntaxError,IndexError,AttributeError):
                pass
            recorded_at = metadata.get("timestamp")
            timing = f"recorded at +{recorded_at:.3f}s · " if recorded_at is not None else ""
            self.step_info.setText(f"Step {row+1} · {self.recorder.serial or 'no recorded device'} · {timing}" +
                                   (f"pre-tap screenshot {evidence.size[0]} × {evidence.size[1]}" if evidence else "No associated screenshot. Record again with capture enabled, or capture a target manually."))
        self.convert_button.setEnabled(self.recorder.state=="stopped" and eligible and evidence is not None)
        self.convert_button.setToolTip("Crop and save a real image from this step's screenshot" if evidence else "No screenshot was captured for this step")
