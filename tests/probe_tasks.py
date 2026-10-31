"""Visible native task controls driving a real isolated simulation worker."""
from pathlib import Path
import json
import sys
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton

from app.automation.qt_service import RuntimeService
from app.simulation.model import SimulationManager
from app.simulation.project import create_project
from app.tasks import TaskStore, TaskScheduler
from app.ui.task_panel import TaskPanel, TaskDialog


def main():
    application=QApplication([])
    root=Path(sys.argv[1])
    simulations=SimulationManager()
    phone=simulations.create()
    project,_=create_project(root/'project',phone.serial,'image')
    runtime=RuntimeService()
    store=TaskStore(root/'tasks.sqlite')
    scheduler=TaskScheduler(store,
        lambda task:runtime.start(task.source,task.serial,trusted=True,backend='simulation',project_root=task.project_root,simulation_config=simulations.config(task.serial)),
        runtime.cancel,lambda serial:serial==phone.serial)
    runtime.event.connect(scheduler.handle_event)
    runtime.snapshot_changed.connect(scheduler.set_busy_serials)
    panel=TaskPanel(store,scheduler,lambda:{'source':'click("start.png")\nprint("Task GUI completed")','serial':phone.serial,'project_root':str(project),'script_id':'<scheduled>'},
                    authorize_callback=lambda task,confirm:confirm())
    panel.resize(1100,750)
    panel.show()
    application.processEvents()
    def click(text):
        widget=next(button for button in panel.findChildren(QPushButton) if button.text()==text)
        assert widget.isVisible() and widget.isEnabled(),text
        QTest.mouseClick(widget,Qt.MouseButton.LeftButton)
        application.processEvents()
    def save_dialog():
        dialog=application.activeModalWidget()
        assert isinstance(dialog,TaskDialog)
        dialog.name.setText('Native scheduled simulation')
        box=dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(box.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    QTimer.singleShot(50,save_dialog)
    click('Create from editor…')
    assert len(store.tasks())==1
    panel.tasks.selectRow(0)
    def approve_dialog():
        dialog=application.activeModalWidget()
        assert dialog is not None
        box=dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(box.button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
    QTimer.singleShot(50,approve_dialog)
    click('Approve source…')
    assert scheduler.is_authorized(store.tasks()[0])
    click('Run now')
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        application.processEvents()
        scheduler.tick()
        if store.history() and store.history()[0]['state']=='completed':break
        time.sleep(.01)
    assert store.history()[0]['state']=='completed',store.history()
    assert simulations.client(phone.serial).state()['screen']=='dashboard'
    click('Pause scheduling')
    assert scheduler.paused
    click('Enable / disable')
    assert not store.tasks()[0].enabled
    panel.close()
    assert runtime.close()
    simulations.close()
    store.close()
    reopened=TaskStore(root/'tasks.sqlite')
    assert reopened.history()[0]['state']=='completed'
    assert reopened.tasks()[0].name=='Native scheduled simulation'
    reopened.close()
    print(json.dumps({'native_task_controls':True,'real_worker_screen_change':True,'persistent_history':True}))


if __name__=='__main__':
    main()
