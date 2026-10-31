"""Native task management over exact, session-approved source snapshots."""
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                              QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit,
                              QMessageBox, QPlainTextEdit, QSpinBox, QSplitter,
                              QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.tasks.store import Task
from app.ui.components import button, label


class TaskDialog(QDialog):
    def __init__(self, task, tasks, parent=None):
        super().__init__(parent)
        self.task = task
        self.result_task = None
        self.setWindowTitle('Automation task')
        self.resize(600, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(label(f'Device: {task.serial}\nScript: {task.script_id}\nSource snapshot: {task.fingerprint[:16]}', 'notice'))
        form = QFormLayout()
        self.name = QLineEdit(task.name)
        self.name.setMaxLength(150)
        form.addRow('Task name', self.name)
        self.enabled = QCheckBox('Enable task')
        self.enabled.setChecked(task.enabled)
        form.addRow('', self.enabled)
        self.schedule = QComboBox()
        self.schedule.addItems(['manual', 'once', 'interval', 'daily', 'weekly'])
        self.schedule.setCurrentText(task.schedule)
        form.addRow('Schedule', self.schedule)
        self.at = QLineEdit(task.at or '')
        self.at.setPlaceholderText('HH:MM or 2026-11-01T09:00:00+00:00')
        form.addRow('Time / one-time date', self.at)
        self.zone = QLineEdit(task.timezone)
        form.addRow('IANA timezone', self.zone)
        self.interval = QSpinBox()
        self.interval.setRange(1,31_536_000)
        self.interval.setValue(task.interval_seconds)
        self.interval.setSuffix(' s')
        form.addRow('Repeating interval', self.interval)
        self.weekdays = QLineEdit(','.join(str(day) for day in task.weekdays))
        form.addRow('Weekdays (Mon=0…Sun=6)', self.weekdays)
        self.priority = QSpinBox()
        self.priority.setRange(-100,100)
        self.priority.setValue(task.priority)
        form.addRow('Priority (higher first)', self.priority)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(.1,86400)
        self.timeout.setValue(task.timeout_seconds)
        self.timeout.setSuffix(' s')
        form.addRow('Execution timeout', self.timeout)
        self.missed = QComboBox()
        self.missed.addItems(['skip','run_once'])
        self.missed.setCurrentText(task.missed)
        form.addRow('Missed runs', self.missed)
        self.dependencies = QLineEdit(','.join(task.dependencies))
        self.dependencies.setToolTip('\n'.join(f'{item.name}: {item.task_id}' for item in tasks if item.task_id != task.task_id) or 'No other tasks')
        form.addRow('Dependency task IDs', self.dependencies)
        self.retries = QSpinBox()
        self.retries.setRange(0,3)
        self.retries.setValue(task.max_retries)
        form.addRow('Whole-script retries', self.retries)
        self.safe = QCheckBox('I confirm the ENTIRE script is safe to repeat')
        self.safe.setChecked(task.restart_safe)
        self.safe.setToolTip('A failed script may already have sent Android actions. Leave disabled unless every operation can safely be repeated. Transport/disconnect failures never restart automatically.')
        form.addRow('', self.safe)
        layout.addLayout(form)
        layout.addWidget(label('Every run executes ordinary Python with your operating-system permissions. Saving does not approve execution. New source snapshots require approval; restart revokes all approval.', 'notice'))
        self.problem = label('', 'notice')
        layout.addWidget(self.problem)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self._save)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

    def _save(self):
        try:
            task = replace(self.task, name=self.name.text().strip(), enabled=self.enabled.isChecked(),
                           schedule=self.schedule.currentText(), at=self.at.text().strip() or None,
                           timezone=self.zone.text().strip(), interval_seconds=self.interval.value(),
                           weekdays=tuple(int(day.strip()) for day in self.weekdays.text().split(',')),
                           priority=self.priority.value(), timeout_seconds=self.timeout.value(),
                           missed=self.missed.currentText(), dependencies=tuple(x.strip() for x in self.dependencies.text().split(',') if x.strip()),
                           max_retries=self.retries.value(), restart_safe=self.safe.isChecked()).validate()
        except (ValueError, TypeError) as error:
            self.problem.setText(str(error))
            return
        self.result_task = task
        self.accept()


class TaskPanel(QWidget):
    def __init__(self, store, scheduler, source_provider, authorize_callback=None, parent=None):
        super().__init__(parent)
        self.store, self.scheduler = store, scheduler
        self.source_provider = source_provider
        self.authorize_callback = authorize_callback
        self._signature = None
        self._history_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16,16,16,16)
        layout.addWidget(label('Persistent automation tasks', 'workspaceTitle'))
        self.status = label('', 'notice')
        layout.addWidget(self.status)
        self.notice = label('Scheduling starts paused. Approve the exact source and device for this session, then resume. Restart, device disconnect and emergency stop revoke approval.', 'notice')
        layout.addWidget(self.notice)
        toolbar = QHBoxLayout()
        toolbar.addWidget(button('Create from editor…', self.create, primary=True))
        toolbar.addWidget(button('Edit…', self.edit))
        toolbar.addWidget(button('Delete…', self.delete))
        toolbar.addWidget(button('Enable / disable', self.toggle_enabled))
        toolbar.addWidget(button('Approve source…', self.authorize))
        layout.addLayout(toolbar)
        runbar = QHBoxLayout()
        runbar.addWidget(button('Replace from editor…', self.replace_source))
        runbar.addWidget(button('Run now', self.run_now))
        runbar.addWidget(button('Cancel task', self.cancel))
        self.pause_button = button('Resume scheduling', self.toggle_pause)
        runbar.addWidget(self.pause_button)
        runbar.addStretch()
        layout.addLayout(runbar)
        split = QSplitter(Qt.Orientation.Vertical)
        self.tasks = QTableWidget(0,7)
        self.tasks.setHorizontalHeaderLabels(['Task','Device','Schedule','Priority','Enabled','Approval','ID'])
        self.tasks.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tasks.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tasks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tasks.setAccessibleName('Persistent automation tasks')
        self.tasks.itemSelectionChanged.connect(self.refresh_history)
        split.addWidget(self.tasks)
        self.history = QTableWidget(0,5)
        self.history.setHorizontalHeaderLabels(['State','Scheduled UTC','Attempt','Run','Result'])
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setAccessibleName('Task execution history')
        split.addWidget(self.history)
        split.setSizes([350,200])
        layout.addWidget(split,1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)
        self.refresh()

    def selected(self):
        row = self.tasks.currentRow()
        if row < 0 or not self.tasks.item(row,0):
            return None
        try:
            return self.store.get(self.tasks.item(row,0).data(Qt.ItemDataRole.UserRole))
        except KeyError:
            return None

    def _perform(self, action):
        try:
            action()
            self.notice.setText('Task state saved locally.')
        except Exception as error:
            self.notice.setText(f'{type(error).__name__}: {error}')
        self._signature = None
        self.refresh()

    def create(self):
        def action():
            snapshot = self.source_provider()
            if snapshot is None:
                raise ValueError('Choose an available device and a script first')
            task = Task(task_id=uuid4().hex, name='New automation task', **snapshot)
            dialog = TaskDialog(task, self.store.tasks(), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.store.save(dialog.result_task)
        self._perform(action)

    def edit(self):
        def action():
            task = self.selected()
            if task is None:
                return
            dialog = TaskDialog(task, self.store.tasks(), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.store.save(dialog.result_task)
                self.scheduler.revoke(task.task_id)
        self._perform(action)

    def replace_source(self):
        def action():
            task = self.selected()
            if task is None:
                return
            snapshot = self.source_provider()
            if snapshot is None:
                raise ValueError('Choose an available device and a script first')
            if QMessageBox.question(self, 'Replace task source', 'Replace this task source and device with the current editor snapshot? Existing approval is revoked.') == QMessageBox.StandardButton.Yes:
                self.store.save(replace(task, **snapshot))
                self.scheduler.revoke(task.task_id)
        self._perform(action)

    def delete(self):
        def action():
            task = self.selected()
            if task and QMessageBox.question(self, 'Delete task', f'Delete {task.name!r} and its execution history? Project scripts and assets are preserved.') == QMessageBox.StandardButton.Yes:
                self.store.delete(task.task_id)
                self.scheduler.revoke(task.task_id)
        self._perform(action)

    def toggle_enabled(self):
        def action():
            task = self.selected()
            if task:
                self.store.save(replace(task, enabled=not task.enabled))
        self._perform(action)

    def _confirm_source(self, task):
        dialog = QDialog(self)
        dialog.setWindowTitle('Approve exact task source and device')
        dialog.resize(740,580)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(f'{task.name}\nDevice: {task.serial}\nProject: {task.project_root}\nSHA-256: {task.fingerprint}\nRetries: {task.max_retries}; whole-script restart approved: {task.restart_safe}', 'notice'))
        layout.addWidget(label('This Python runs with your operating-system permissions. Approval applies to this exact source and target for this application session. Review all imports and actions before approving.', 'notice'))
        source = QPlainTextEdit()
        source.setReadOnly(True)
        source.setPlainText(task.source)
        layout.addWidget(source,1)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Ok).setText('Approve this source and device')
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        layout.addWidget(actions)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def authorize(self):
        def action():
            task = self.selected()
            if task is None:
                return
            confirm = lambda: self._confirm_source(task)
            approved = self.authorize_callback(task, confirm) if self.authorize_callback else False
            if approved:
                # Recheck the persisted fingerprint after the modal event loop.
                if self.store.get(task.task_id).fingerprint != task.fingerprint:
                    raise ValueError('Task changed during approval; review it again')
                self.scheduler.authorize(task.task_id)
        self._perform(action)

    def run_now(self):
        def action():
            task = self.selected()
            if task:
                self.scheduler.run_now(task.task_id)
                self.scheduler.resume()
                self.scheduler.tick()
        self._perform(action)

    def cancel(self):
        def action():
            task = self.selected()
            if task:
                self.scheduler.cancel_task(task.task_id)
        self._perform(action)

    def toggle_pause(self):
        self.scheduler.resume() if self.scheduler.paused else self.scheduler.pause()
        self.refresh()

    def refresh(self):
        tasks = self.store.tasks()
        signature = tuple((task, self.scheduler.is_authorized(task)) for task in tasks)
        self.status.setText(f'Scheduling {"paused" if self.scheduler.paused else "active"} · {len(tasks)} task(s) · data: {self.store.path}')
        self.pause_button.setText('Resume scheduling' if self.scheduler.paused else 'Pause scheduling')
        if signature != self._signature:
            selected = self.selected()
            self.tasks.setRowCount(len(tasks))
            for row, task in enumerate(tasks):
                values = (task.name, task.serial, task.schedule, str(task.priority), 'Yes' if task.enabled else 'No', 'Approved' if self.scheduler.is_authorized(task) else 'Required', task.task_id)
                for column,value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole,task.task_id)
                    self.tasks.setItem(row,column,item)
                if selected and selected.task_id == task.task_id:
                    self.tasks.selectRow(row)
            self.tasks.resizeColumnsToContents()
            self._signature = signature
        self.refresh_history()

    def refresh_history(self):
        from datetime import datetime, timezone
        task = self.selected()
        history = self.store.history(task.task_id if task else None)
        signature = repr(history)
        if signature == self._history_signature:
            return
        self._history_signature = signature
        self.history.setRowCount(len(history))
        for row, execution in enumerate(history):
            values = (execution['state'], datetime.fromtimestamp(execution['scheduled'],timezone.utc).isoformat(timespec='seconds'), str(execution['attempt']), execution['run_id'] or '', execution['message'])
            for column,value in enumerate(values):
                self.history.setItem(row,column,QTableWidgetItem(value))
        self.history.resizeColumnsToContents()
