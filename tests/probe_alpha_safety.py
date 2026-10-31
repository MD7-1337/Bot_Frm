"""Real StudioWindow safety regressions; no Android hardware is represented."""
from pathlib import Path
import json
import os
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from app.tasks import Task
from app.ui.window import StudioWindow
from probe_device_workbench import spin


def main():
    root=Path(sys.argv[1]);mode=sys.argv[2]
    root.mkdir(parents=True,exist_ok=True)
    data=root/'data';data.mkdir()
    os.environ['STUDIO_DATA_DIR']=str(data)
    os.environ['STUDIO_CONFIG_DIR']=str(root/'config')
    corrupted={}
    if mode=='corrupt':
        for name in ('tasks.sqlite3','failures.sqlite3'):
            content=b'preserve corrupt user database exactly:'+name.encode()+bytes(range(64))
            (data/name).write_bytes(content)
            corrupted[name]=content
    application=QApplication([])
    application.setQuitOnLastWindowClosed(False)
    window=StudioWindow(discover=False)
    window.resize(1400,900);window.show()
    warning=QMessageBox.warning
    result={}
    try:
        spin(application,lambda:window.editor.is_ready and not window.jobs,timeout=25)
        if mode=='corrupt':
            assert window.task_store is None and window.recovery_journal is None
            assert isinstance(window.task_panel,QLabel) and isinstance(window.recovery_panel,QLabel)
            assert not window.task_panel.findChildren(QPushButton)
            assert window.scheduler.paused
            source='# Local editing remains available\nmessage = "retained data"\n'
            window.editor.set_text(source)
            actual=[]
            window.editor.page.runJavaScript('window.studio.editor.getValue()',actual.append)
            spin(application,lambda:bool(actual))
            assert actual[0]==source
            for name,content in corrupted.items():assert (data/name).read_bytes()==content
            result['corrupt_databases_preserved']=True
            result['monaco_editing_after_corruption']=True
        else:
            native=[]
            def forbidden(*args,**kwargs):
                native.append(args)
                raise AssertionError('Simulation reached physical ADB')
            window.adb.tap=window.adb.swipe=window.adb.key=window.adb.screenshot=forbidden
            window.start_demo()
            spin(application,lambda:window.active_simulation is not None and not window._demo_pending and window.preview.frame is not None and not window.jobs)
            serial=window.active_simulation
            if mode=='stale':
                source='click("start.png")\n'
                window.editor.set_text(source)
                before=len(window.run_states)
                original=window._connection_token(serial)
                def reset_during_approval(*args,**kwargs):
                    window.reset_demo()
                    spin(application,lambda:not window._demo_pending and not window.jobs)
                    return QMessageBox.StandardButton.Yes
                QMessageBox.warning=reset_during_approval
                window._approve_and_run([(serial,source,'<editor>',window.project_root)])
                assert original.is_set() and window._connection_token(serial) is not original
                assert not window.pending_runs and len(window.run_states)==before
                assert window.simulations.client(serial).state()['actions']==0
                assert 'became unavailable or busy; no run queued' in window.logs.toPlainText()
                task=Task('modal-safety','Modal source snapshot',source,serial,str(window.project_root))
                window.task_store.save(task)
                original=window._connection_token(serial)
                def reset_task_confirmation():
                    window.reset_demo()
                    spin(application,lambda:not window._demo_pending and not window.jobs)
                    return True
                assert window._authorize_task(task,reset_task_confirmation) is False
                assert original.is_set() and window._connection_token(serial) is not original
                assert task.task_id not in window._task_connections
                assert not window.scheduler.is_authorized(task)
                assert window.simulations.client(serial).state()['actions']==0
                result['run_approval_rejects_reset_connection']=True
                result['task_approval_rejects_reset_connection']=True
            elif mode=='evidence':
                window.show_workspace('monitor')
                window.shell.monitor_tabs.setCurrentWidget(window.recovery_panel)
                application.processEvents()
                capture=window.recovery_panel.capture_failures
                assert capture.isVisible() and capture.isEnabled()
                QTest.mouseClick(capture,Qt.MouseButton.LeftButton,pos=QPoint(8,capture.height()//2))
                assert capture.isChecked()
                window.show_workspace('studio')
                # Freeze the preview at START, then change the simulator in an
                # actual worker before failure. Persisted evidence must come
                # from a fresh capture of DASHBOARD, never the stale preview.
                window.simulation_timer.stop()
                spin(application,lambda:not window.jobs)
                stale=window.preview.frame.png
                source='click("start.png")\nraise RuntimeError("fresh postfailure evidence")\n'
                window.editor.set_text(source)
                QMessageBox.warning=lambda *args,**kwargs:QMessageBox.StandardButton.Yes
                window.run_selected_scripts()
                spin(application,lambda:bool(window.run_states) and window.run_states[-1].state=='failed' and window.run_states[-1].exitcode is not None and not window.jobs)
                records=window.recovery_journal.recent()
                assert len(records)==1,records
                record=window.recovery_journal.detail(records[0]['id'],include_screenshot=True)
                assert record['run_id']==window.run_states[-1].run_id
                assert record['error_type']=='RuntimeError' and record['message']=='fresh postfailure evidence'
                assert record['source_line']==2
                assert record['screenshot'] and record['width']==360 and record['height']==720
                assert record['screenshot']!=stale
                assert record['screenshot']==window.capture_device(serial).png
                assert window.simulations.client(serial).state()['screen']=='dashboard'
                assert window.preview.frame.png==stale
                window.recovery_panel.refresh()
                assert window.recovery_panel.table.rowCount()==1
                result['actual_worker_failure_persisted']=True
                result['fresh_postfailure_capture_preserves_identity']=True
            else:
                raise ValueError(mode)
            assert not native
    finally:
        QMessageBox.warning=warning
        window.shell.documents.remember()
        for document in window.shell.documents.documents:document.saved=document.source
        window.saved_source=window.editor.source
        window.close()
        spin(application,lambda:window._shutdown_complete,timeout=20)
    for name,content in corrupted.items():assert (data/name).read_bytes()==content
    print(json.dumps(result))


if __name__=='__main__':main()
