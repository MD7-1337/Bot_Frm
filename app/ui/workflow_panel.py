"""Native ordered workflow and explicit device-group editor; never autoapproves."""
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,
    QInputDialog,QLineEdit,QListWidget,QMessageBox,QPlainTextEdit,QSpinBox,QTabWidget,QVBoxLayout,QWidget)

from app.tasks import Task
from app.tasks.workflows import Workflow
from app.ui.components import button,label


class WorkflowDialog(QDialog):
    def __init__(self, store, workflow=None, parent=None):
        super().__init__(parent)
        self.store=store
        self.workflow=workflow or Workflow(uuid4().hex,'New workflow',())
        self.result_workflow=None
        self.setWindowTitle('Ordered automation workflow')
        self.resize(700,680)
        layout=QVBoxLayout(self)
        form=QFormLayout()
        self.name=QLineEdit(self.workflow.name);form.addRow('Name',self.name)
        self.enabled=QCheckBox('Enable workflow');self.enabled.setChecked(self.workflow.enabled);form.addRow('',self.enabled)
        self.schedule=QComboBox();self.schedule.addItems(['manual','once','interval','daily','weekly']);self.schedule.setCurrentText(self.workflow.schedule);form.addRow('Schedule',self.schedule)
        self.at=QLineEdit(self.workflow.at or '');self.at.setPlaceholderText('HH:MM or ISO date including UTC offset');form.addRow('Time',self.at)
        self.zone=QLineEdit(self.workflow.timezone);form.addRow('Timezone',self.zone)
        self.interval=QSpinBox();self.interval.setRange(1,31_536_000);self.interval.setValue(self.workflow.interval_seconds);form.addRow('Interval seconds',self.interval)
        self.days=QLineEdit(','.join(map(str,self.workflow.weekdays)));form.addRow('Weekdays (Monday=0)',self.days)
        self.missed=QComboBox();self.missed.addItems(['skip','run_once']);self.missed.setCurrentText(self.workflow.missed);form.addRow('Missed runs',self.missed)
        layout.addLayout(form)
        layout.addWidget(label('Each step runs only after the preceding step in this same occurrence succeeds. Failures/cancellation stop the sequence. Use manual tasks; schedule the whole workflow here.','notice'))
        row=QHBoxLayout()
        self.available=QComboBox()
        for task in store.tasks():
            if task.schedule=='manual':self.available.addItem(f'{task.name} · {task.serial}',task.task_id)
        row.addWidget(self.available,1);row.addWidget(button('Add step',self.add));layout.addLayout(row)
        self.steps=QListWidget();self.steps.setAccessibleName('Ordered workflow steps');layout.addWidget(self.steps,1)
        for identity in self.workflow.task_ids:self.append(identity)
        controls=QHBoxLayout()
        controls.addWidget(button('Move up',lambda:self.move(-1)));controls.addWidget(button('Move down',lambda:self.move(1)))
        controls.addWidget(button('Remove step',lambda:self.steps.takeItem(self.steps.currentRow())));layout.addLayout(controls)
        self.problem=label('','notice');layout.addWidget(self.problem)
        actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.save);actions.rejected.connect(self.reject);layout.addWidget(actions)

    def append(self,identity):
        from PySide6.QtWidgets import QListWidgetItem
        task=self.store.get(identity)
        item=QListWidgetItem(f'{task.name} · {task.serial}');item.setData(Qt.ItemDataRole.UserRole,identity);self.steps.addItem(item)

    def add(self):
        if self.available.currentData():self.append(self.available.currentData())

    def move(self,offset):
        index=self.steps.currentRow();target=index+offset
        if index>=0 and 0<=target<self.steps.count():
            item=self.steps.takeItem(index);self.steps.insertItem(target,item);self.steps.setCurrentRow(target)

    def save(self):
        try:
            candidate=replace(self.workflow,name=self.name.text().strip(),enabled=self.enabled.isChecked(),
                task_ids=tuple(self.steps.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.steps.count())),
                schedule=self.schedule.currentText(),at=self.at.text().strip() or None,timezone=self.zone.text().strip(),
                interval_seconds=self.interval.value(),weekdays=tuple(int(x.strip()) for x in self.days.text().split(',')),missed=self.missed.currentText()).validate()
            self.store.save_workflow(candidate)
            self.result_workflow=candidate;self.accept()
        except Exception as error:self.problem.setText(str(error))


class WorkflowPanel(QWidget):
    def __init__(self, tasks, group_provider=None, parent=None):
        super().__init__(parent)
        self.host=tasks;self.store=tasks.store;self.scheduler=tasks.scheduler;self.group_provider=group_provider
        layout=QVBoxLayout(self)
        tabs=QTabWidget();layout.addWidget(tabs)
        groups=QWidget();gl=QVBoxLayout(groups)
        gl.addWidget(label('Named groups contain exact device identities. Copying an editor snapshot creates separate tasks; every source/device still needs approval.','notice'))
        self.group_name=QComboBox();self.group_name.setEditable(True);gl.addWidget(self.group_name)
        self.members=QPlainTextEdit();self.members.setPlaceholderText('One exact ADB serial or sim:// identity per line');gl.addWidget(self.members)
        row=QHBoxLayout()
        for title,action in [('Save group',self.save_group),('Delete group',self.delete_group),('Load device labels',self.load_labels),('Use task devices',self.task_devices),('Create group tasks…',self.create_group_tasks)]:row.addWidget(button(title,action))
        gl.addLayout(row);tabs.addTab(groups,'Device groups')
        wf=QWidget();wl=QVBoxLayout(wf)
        self.workflows=QListWidget();self.workflows.setAccessibleName('Saved ordered workflows');wl.addWidget(self.workflows,1)
        row=QHBoxLayout()
        for title,action in [('New workflow…',self.new),('Edit…',self.edit),('Delete…',self.delete),('Approve steps…',self.approve),('Run workflow',self.run),('Cancel workflow',self.cancel)]:row.addWidget(button(title,action))
        wl.addLayout(row)
        self.history=QListWidget();self.history.setAccessibleName('Workflow occurrence history');wl.addWidget(self.history,1)
        wl.addWidget(button('Refresh workflow history',self.refresh));tabs.addTab(wf,'Sequential workflows')
        self.notice=label('','notice');layout.addWidget(self.notice)
        self.group_name.currentIndexChanged.connect(self.load_group)
        self.workflows.currentItemChanged.connect(lambda *_:self.refresh_history())
        self.refresh()
        self.timer=QTimer(self)
        self.timer.timeout.connect(lambda:self.refresh_history() if self.isVisible() else None)
        self.timer.start(500)

    def perform(self,action):
        try:action()
        except Exception as error:self.notice.setText(str(error))
        self.host.refresh();self.refresh()

    def selected(self):
        item=self.workflows.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self):
        current=self.selected();self.workflows.clear()
        for workflow in self.store.workflows():
            from PySide6.QtWidgets import QListWidgetItem
            item=QListWidgetItem(f'{workflow.name} · {len(workflow.task_ids)} steps · {workflow.schedule} · '+('approved' if self.scheduler.workflow_authorized(workflow) else 'approval required'))
            item.setData(Qt.ItemDataRole.UserRole,workflow.workflow_id);self.workflows.addItem(item)
            if workflow.workflow_id==current:self.workflows.setCurrentItem(item)
        group=self.group_name.currentText();self.group_name.blockSignals(True);self.group_name.clear();self.group_name.addItems(self.store.groups());self.group_name.setCurrentText(group);self.group_name.blockSignals(False)
        self.refresh_history()

    def refresh_history(self):
        self.history.clear()
        for row in self.store.workflow_history(self.selected()):
            self.history.addItem(f"{row['state']} · {row['id'][:10]} · {row['message']}")

    def load_group(self,*_):
        members=self.store.groups().get(self.group_name.currentText())
        if members:self.members.setPlainText('\n'.join(members))

    def save_group(self):
        self.perform(lambda:self.store.save_group(self.group_name.currentText(),tuple(x.strip() for x in self.members.toPlainText().splitlines() if x.strip())))

    def delete_group(self):
        def action():
            if QMessageBox.question(self,'Delete group','Delete this group definition? Existing tasks and devices are preserved.')==QMessageBox.StandardButton.Yes:self.store.delete_group(self.group_name.currentText())
        self.perform(action)

    def load_labels(self):
        def action():
            if not self.group_provider:raise ValueError('No Device Manager groups were supplied; enter explicit members or use task devices')
            groups=self.group_provider()
            if not groups:raise ValueError('Save group labels in Device Manager first')
            name,ok=QInputDialog.getItem(self,'Device Manager groups','Choose group',list(groups),editable=False)
            if ok:self.group_name.setCurrentText(name);self.members.setPlainText('\n'.join(groups[name]))
        self.perform(action)

    def task_devices(self):
        self.members.setPlainText('\n'.join(dict.fromkeys(task.serial for task in self.store.tasks())))

    def create_group_tasks(self):
        def action():
            from app.ui.task_panel import TaskDialog
            snapshot=self.host.source_provider()
            template=Task(uuid4().hex,'Group automation',**snapshot)
            dialog=TaskDialog(template,self.store.tasks(),self)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                tasks=self.store.expand_group(self.group_name.currentText(),dialog.result_task)
                self.notice.setText(f'Created {len(tasks)} exact-device tasks. Review and approve each source/device in Task Manager.')
        self.perform(action)

    def new(self):self.perform(lambda:WorkflowDialog(self.store,parent=self).exec())
    def edit(self):
        if self.selected():self.perform(lambda:WorkflowDialog(self.store,self.store.workflow(self.selected()),self).exec())
    def delete(self):
        def action():
            if self.selected() and QMessageBox.question(self,'Delete workflow','Delete the workflow definition/history? Task definitions remain saved.')==QMessageBox.StandardButton.Yes:self.store.delete_workflow(self.selected())
        self.perform(action)

    def approve(self):
        def action():
            identity=self.selected()
            if not identity:return
            workflow=self.store.workflow(identity);fingerprint=self.scheduler.workflow_fingerprint(workflow)
            listing='\n'.join(f'{i+1}. {self.store.get(task).name} · {self.store.get(task).serial}' for i,task in enumerate(workflow.task_ids))
            if QMessageBox.warning(self,'Approve ordered workflow',f'{workflow.name} · {workflow.schedule}\n{listing}\n\nReview every source/device next. This approves repeated scheduled occurrences for this session. A failed or uncertain step stops the sequence.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
            for task_id in dict.fromkeys(workflow.task_ids):
                task=self.store.get(task_id)
                if not self.host.authorize_callback or not self.host.authorize_callback(task,lambda current=task:self.host._confirm_source(current)):return
                if self.store.get(task_id).fingerprint!=task.fingerprint:raise ValueError('Task changed during approval')
                self.scheduler.authorize(task_id)
            if self.scheduler.workflow_fingerprint(self.store.workflow(identity))!=fingerprint:raise ValueError('Workflow changed during approval')
            self.scheduler.authorize_workflow(identity)
            self.notice.setText('Workflow sources and device connections approved for this session')
        self.perform(action)

    def run(self):
        def action():
            if self.selected():self.scheduler.run_workflow(self.selected());self.scheduler.resume();self.scheduler.tick()
        self.perform(action)

    def cancel(self):
        if self.selected():self.perform(lambda:self.scheduler.cancel_workflow(self.selected()))
