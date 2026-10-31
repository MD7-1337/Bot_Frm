"""Native group/sequence editor, real trusted workers, and durable per-run history."""
from pathlib import Path
import json
import sys
import time

from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox,QPushButton,QTabWidget
from app.automation.qt_service import RuntimeService
from app.simulation.model import SimulationManager
from app.simulation.project import create_project
from app.tasks import TaskStore,TaskScheduler
from app.ui.task_panel import TaskPanel,TaskDialog
from app.ui.workflow_panel import WorkflowPanel,WorkflowDialog


def main():
    app=QApplication([]);root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
    manager=SimulationManager();phones=[manager.create(),manager.create()]
    project,_=create_project(root/'project',phones[0].serial,'image')
    runtime=RuntimeService(max_workers=2);store=TaskStore(root/'tasks.sqlite')
    scheduler=TaskScheduler(store,lambda task:runtime.start(task.source,task.serial,trusted=True,backend='simulation',project_root=task.project_root,simulation_config=manager.config(task.serial)),runtime.cancel,lambda serial:manager.get(serial).available)
    runtime.event.connect(scheduler.handle_event);runtime.snapshot_changed.connect(scheduler.set_busy_serials)
    tasks=TaskPanel(store,scheduler,lambda:{'source':'click("start.png")','serial':phones[0].serial,'project_root':str(project),'script_id':'<scheduled>'},authorize_callback=lambda task,confirm:confirm())
    panel=WorkflowPanel(tasks);panel.resize(1300,800);panel.show();app.processEvents()
    def click(owner,title):
        button=next(item for item in owner.findChildren(QPushButton) if item.text()==title)
        assert button.isVisible() and button.isEnabled(),title
        print('Click:',title,flush=True)
        QTest.mouseClick(button,Qt.MouseButton.LeftButton);app.processEvents()
    panel.group_name.setCurrentText('Two offline phones')
    panel.members.setPlainText('\n'.join(phone.serial for phone in phones));click(panel,'Save group')
    assert len(store.groups()['Two offline phones'])==2
    def create_tasks():
        dialog=app.activeModalWidget();assert isinstance(dialog,TaskDialog)
        dialog.name.setText('Click demo target')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    QTimer.singleShot(50,create_tasks);click(panel,'Create group tasks…')
    assert len(store.tasks())==2 and not scheduler.authorized
    panel.findChild(QTabWidget).setCurrentIndex(1)
    def create_workflow():
        dialog=app.activeModalWidget();assert isinstance(dialog,WorkflowDialog)
        dialog.name.setText('Two phone sequential validation')
        dialog.available.setCurrentIndex(0);click(dialog,'Add step')
        dialog.available.setCurrentIndex(1);click(dialog,'Add step')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    QTimer.singleShot(50,create_workflow);click(panel,'New workflow…')
    assert len(store.workflows())==1;panel.workflows.setCurrentRow(0)
    handled=[]
    def approve():
        dialog=app.activeModalWidget()
        if dialog is None or dialog in handled:return
        print('Modal:',dialog.windowTitle(),flush=True)
        if isinstance(dialog,QMessageBox):
            handled.append(dialog);dialog.button(QMessageBox.StandardButton.Yes).click()
        elif dialog.findChild(QDialogButtonBox):
            handled.append(dialog);dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    approval=QTimer();approval.timeout.connect(approve);approval.start(30)
    click(panel,'Approve steps…');approval.stop()
    assert scheduler.workflow_authorized(store.workflows()[0])
    click(panel,'Run workflow')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        app.processEvents();scheduler.tick()
        if store.workflow_history()[0]['state']=='completed':break
        time.sleep(.01)
    assert store.workflow_history()[0]['state']=='completed',store.workflow_history()
    assert all(manager.client(phone.serial).state()['screen']=='dashboard' for phone in phones)
    click(panel,'Refresh workflow history')
    assert panel.history.item(0).text().startswith('completed')
    panel.timer.stop();tasks.timer.stop();panel.close();tasks.close()
    assert runtime.close();manager.close();store.close()
    reopened=TaskStore(root/'tasks.sqlite')
    assert reopened.workflow_history()[0]['state']=='completed'
    fresh=TaskScheduler(reopened,lambda _:None,lambda _:None,lambda _:True)
    assert not fresh.workflow_authorized(reopened.workflows()[0]);reopened.close()
    print(json.dumps({'native_group_expansion':True,'ordered_editor':True,'actual_independent_workers':True,'durable_occurrence_history':True,'restart_revokes_workflow_approval':True}))

if __name__=='__main__':main()
