"""Real Qt + Monaco + actual simulation workers; never a physical Android test."""
from pathlib import Path
import ast
import json
import os
import shutil
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.ui.window import StudioWindow
from app.ui.capture_dialog import CaptureDialog
from app.ui.recognition_inspector import RecognitionInspector
from app.simulation.model import LABEL
from app.vision.matching import Region
from probe_device_workbench import spin
from probe_alpha_ux import click, navigation, toolbar


def main():
    directory=Path(sys.argv[1]); directory.mkdir(exist_ok=True,parents=True)
    screenshots=Path(sys.argv[2]) if len(sys.argv)>2 else None
    if screenshots: screenshots.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    app=QApplication([]); app.setQuitOnLastWindowClosed(False)
    ticks=[]
    heartbeat=QTimer(); heartbeat.setInterval(10);heartbeat.timeout.connect(lambda:ticks.append(time.perf_counter()));heartbeat.start()
    window=StudioWindow(discover=False)
    window.resize(1440,960); window.show()
    events=[]; window.runtime.event.connect(events.append)
    # Any accidental native input or capture from these demos is a test failure.
    native_calls=[]
    def forbidden(*args,**kwargs):
        native_calls.append(args); raise AssertionError('Simulation dispatched to ADB')
    window.adb.tap=window.adb.swipe=window.adb.key=window.adb.screenshot=forbidden
    warning,question=QMessageBox.warning,QMessageBox.question
    get_save=QFileDialog.getSaveFileName
    QMessageBox.warning=QMessageBox.question=lambda *a,**k:QMessageBox.StandardButton.Yes
    try:
        spin(app,lambda:window.editor.is_ready and not window.jobs)
        startup_ms=1000*(time.perf_counter()-started)
        navigation(window,'devices')
        window.device_manager.tabs.setCurrentWidget(window.simulation_panel)
        click(window.simulation_panel,'Start Demo Session')
        spin(app,lambda:window.active_simulation is not None and window.preview.frame is not None and not window._demo_pending)
        one=window.active_simulation; root=window.project_root
        for widget in (window.live_panel.start_button,window.live_panel.stop_button,window.live_panel.home_button,window.live_panel.back_button,window.live_panel.capture_button):
            if not window.rect().contains(widget.mapTo(window,widget.rect().bottomRight())):
                if diagnostic_dir := os.environ.get('STUDIO_SCREENSHOT_DIR'):
                    diagnostic_dir = Path(diagnostic_dir)
                    diagnostic_dir.mkdir(parents=True, exist_ok=True)
                    window.grab().save(str(diagnostic_dir/'phase6-clipped-controls.png'))
                raise AssertionError({'control': widget.text(), 'geometry': widget.geometry().getRect(),
                    'bottom_right': widget.mapTo(window,widget.rect().bottomRight()).toTuple(),
                    'panel': window.live_panel.geometry().getRect(), 'window': window.rect().getRect()})
        assert window.registry.snapshot()==[] and window.devices.count()==0
        assert window.preview.frame.transport=='simulation'
        assert window.shell.simulation_notice.isVisible() and LABEL in window.shell.simulation_notice.text()
        assert (root/'images/start.png').exists() and 'click("start.png")' in window.editor.source
        spin(app,lambda:not window.jobs)
        window._sync_controls(); toolbar(window,'run')
        spin(app,lambda:bool(window.run_states) and window.run_states[-1].exitcode is not None)
        assert window.run_states[-1].state=='completed',events
        assert window.run_states[-1].backend=='simulation'
        assert all(e['source_path']==str(root/'scripts/image.py') for e in events if e.get('event')=='line')
        assert window.simulations.client(one).state()['screen']=='dashboard'
        if screenshots:
            QTest.qWait(200); window.grab().save(str(screenshots/'phase6-demo-studio.png'))

        navigation(window,'devices'); window.device_manager.tabs.setCurrentWidget(window.simulation_panel)
        click(window.simulation_panel,'Reset Demo')
        spin(app,lambda:not window._demo_pending and window.simulations.client(one).state()['screen']=='start')
        spin(app,lambda:window.preview.frame is not None)
        navigation(window,'visual')
        click(window.visual_tools,'Inspect text / color / pixels…')
        spin(app,lambda:any(isinstance(d,RecognitionInspector) for d in window._capture_dialogs))
        inspector=next(d for d in window._capture_dialogs if isinstance(d,RecognitionInspector))
        inspector.image_path.setText('start.png')
        tested=[]; inspector.tested.connect(tested.append)
        click(inspector,'Test recognition'); spin(app,lambda:len(tested)==1)
        assert not tested[-1]['error'] and tested[-1]['matches'][0].region==Region(60,480,240,64),tested
        point=QPoint(*map(round,inspector.canvas.viewport().from_device(70,490)))
        QTest.mouseClick(inspector.canvas,Qt.MouseButton.LeftButton,pos=point); QTest.qWait(60)
        assert inspector._pixel is not None and abs(inspector._pixel[0]-70)<=1 and abs(inspector._pixel[1]-490)<=1,inspector._pixel
        click(inspector,'Insert selected pixel code')
        spin(app,lambda:f'getPixel({inspector._pixel[0]}, {inspector._pixel[1]})' in window.editor.source)
        inspector.tabs.setCurrentIndex(2)
        click(inspector,'Test recognition'); spin(app,lambda:len(tested)==2)
        assert not tested[-1]['error'] and tested[-1]['matches']
        click(inspector,'Insert recognition Python')
        spin(app,lambda:'findColor(' in window.editor.source)
        if shutil.which('tesseract'):
            inspector.tabs.setCurrentIndex(1); inspector.query.setText('START')
            inspector.use_region.setChecked(True); inspector.canvas.set_selection(Region(60,480,240,64))
            click(inspector,'Test recognition'); spin(app,lambda:len(tested)==3)
            assert not tested[-1]['error'] and tested[-1]['matches'],tested[-1]
        if screenshots:
            inspector.grab().save(str(screenshots/'phase6-recognition.png'))
        inspector.reject(); spin(app,lambda:inspector not in window._capture_dialogs)

        navigation(window,'recorder'); window._sync_controls()
        click(window.recorder_panel,'Start on current phone')
        spin(app,lambda:window.preview.frame is not None)
        QTest.qWait(150)
        point=QPoint(*map(round,window.preview.viewport().from_device(180,512)))
        QTest.mouseClick(window.preview,Qt.MouseButton.LeftButton,pos=point)
        spin(app,lambda:bool(window.recorder.actions) and not window.pending_controls)
        assert window.simulations.client(one).state()['screen']=='dashboard'
        click(window.recorder_panel,'Stop recording'); window._sync_controls()
        panel=window.recorder_panel; panel.table.selectRow(0)
        assert window.recorder.evidence[0].size==(360,720)
        recorded_tap = ast.parse(panel.table.item(0,0).text()).body[0].value
        recorded_x, recorded_y = (ast.literal_eval(argument) for argument in recorded_tap.args)
        click(panel,'Convert to Image Target…')
        spin(app,lambda:any(isinstance(d,CaptureDialog) for d in window._capture_dialogs))
        capture=next(d for d in window._capture_dialogs if isinstance(d,CaptureDialog))
        capture.select_region(Region(60,480,240,64))
        target=root/'images/recorded-start.png'
        QFileDialog.getSaveFileName=lambda *a,**k:(str(target),'PNG')
        click(capture,'Save crop + insert reference…')
        spin(app,lambda:panel.table.item(0,0).text().startswith('click('))
        # A downscaled preview maps an integer Qt pointer back to device pixels;
        # the acknowledged tap may be a pixel off the crop center. Conversion
        # must preserve that actual tap, including its offset, rather than snap.
        dx, dy = recorded_x - 180, recorded_y - 512
        argument = '"images/recorded-start.png"'
        if dx or dy:
            argument = f'Pattern({argument}).targetOffset({dx}, {dy})'
        assert target.exists() and panel.table.item(0,0).text()==f'click({argument})', {
            'target': str(target), 'exists': target.exists(),
            'step': panel.table.item(0,0).text(), 'logs': window.logs.toPlainText()[-2000:]}
        capture.reject(); spin(app,lambda:capture not in window._capture_dialogs)
        # Metadata follows each whole row when reordered and deleted.
        panel.delay.setValue(.01); click(panel,'Add delay')
        click(panel,'Move up'); assert panel.table.item(0,0).text().startswith('sleep(')
        click(panel,'Move down'); panel.table.selectRow(1); click(panel,'Delete step')
        panel.table.selectRow(0)
        source=panel.source(); compile(source,'<demo-recording>','exec')
        session=root/'recording.json'; session.write_text(window.recorder.session_json(),encoding='utf-8')
        window.recorder.load_session(session.read_text(encoding='utf-8')); panel.refresh(reset=True)
        assert window.recorder.evidence[0].size==(360,720)
        click(panel,'Insert Python into Monaco')
        spin(app,lambda:'recorded-start.png' in window.editor.source)
        if screenshots:
            QTest.qWait(120); window.grab().save(str(screenshots/'phase6-recorder.png'))
        navigation(window,'devices'); window.device_manager.tabs.setCurrentWidget(window.simulation_panel)
        click(window.simulation_panel,'Reset Demo'); spin(app,lambda:not window._demo_pending)
        navigation(window,'recorder'); window._sync_controls(); before=len(window.run_states)
        click(panel,'Replay on selected phone…')
        spin(app,lambda:len(window.run_states)>before and window.run_states[-1].exitcode is not None)
        assert window.run_states[-1].state=='completed',events
        assert window.simulations.client(one).state()['screen']=='dashboard'

        # Pause/resume and emergency stop use the actual isolated execution path.
        navigation(window,'studio'); window.editor.set_text('while True:\n    capture()\n    sleep(.03)\n')
        QTest.qWait(100); window._sync_controls(); toolbar(window,'run')
        spin(app,lambda:window.run_states[-1].state=='running')
        toolbar(window,'pause'); spin(app,lambda:window.run_states[-1].state=='paused')
        toolbar(window,'resume'); spin(app,lambda:window.run_states[-1].state=='running')
        QTest.mouseClick(window.shell.emergency,Qt.MouseButton.LeftButton)
        spin(app,lambda:window.run_states[-1].exitcode is not None and window.reset_stop_action.isEnabled())
        assert window.run_states[-1].state=='cancelled'
        window.reset_stop_action.trigger(); spin(app,lambda:not window._emergency_latched)

        # Real worker failure inspection and Monaco source navigation, with no retries.
        window.editor.set_text('# deliberate no-match\nwaitImage("reward.png", timeout=.05)\n')
        QTest.qWait(100); window._sync_controls(); toolbar(window,'run')
        spin(app,lambda:window.run_states[-1].state=='failed' and window.run_states[-1].exitcode is not None)
        failed_id=window.run_states[-1].run_id
        failure=window.execution_panel.failures[failed_id]
        assert failure['failure']['category']=='recognition' and failure['failure']['automatic_retry'] is False
        navigation(window,'monitor')
        row=window.execution_panel.rows[failed_id]
        item=window.execution_panel.table.item(row,4)
        assert 'recognition' in item.toolTip()
        window.execution_panel.table.scrollToItem(item);QTest.qWait(50)
        point=window.execution_panel.table.visualItemRect(item).center()
        QTest.mouseClick(window.execution_panel.table.viewport(),Qt.MouseButton.LeftButton,pos=point)
        QTest.mouseDClick(window.execution_panel.table.viewport(),Qt.MouseButton.LeftButton,pos=point)
        spin(app,lambda:window.shell.current=='studio')
        position=[]
        window.editor.page.runJavaScript('window.studio.editor.getPosition().lineNumber',position.append)
        spin(app,lambda:bool(position));assert position[0]==2,position
        window.editor.set_text('# edited after failure\n')
        QTest.qWait(80);window.inspect_run_failure(failed_id)
        assert window.editor.source=='# edited after failure\n'
        assert 'older source snapshot' in window.shell.notification.text()

        # A second explicitly-created session has its own state, pixels and context.
        navigation(window,'devices'); window.device_manager.tabs.setCurrentWidget(window.simulation_panel)
        window.simulation_panel.scenario.setCurrentIndex(2)
        click(window.simulation_panel,'Start Demo Session')
        spin(app,lambda:window.active_simulation!=one and not window._demo_pending)
        two=window.active_simulation
        assert window.simulations.client(two).state()['screen']=='start'
        assert window.simulations.client(one).state()['screen']=='dashboard'
        spin(app,lambda:window.preview.frame is not None and window.preview.frame.serial==two)
        window._sync_controls(); toolbar(window,'run')
        spin(app,lambda:window.run_states[-1].serial==two and window.run_states[-1].exitcode is not None)
        assert window.run_states[-1].state=='completed',events
        assert window.simulations.client(two).state()['screen']=='complete'
        assert window.simulations.client(one).state()['screen']=='dashboard'
        navigation(window,'devices'); window.device_manager.tabs.setCurrentWidget(window.simulation_panel)
        if screenshots:
            QTest.qWait(120);window.grab().save(str(screenshots/'phase6-simulation-controls.png'))
        click(window.simulation_panel,'Stop Demo'); spin(app,lambda:not window._demo_pending)
        assert not window.simulations.get(two).available
        assert window.registry.snapshot()==[] and not native_calls
        for width,height in ((1100,760),(1024,700)):
            window.resize(width,height);QTest.qWait(120)
            assert window.width()<=width,(width,window.width())
            for name in ('studio','devices','visual','recorder','settings'):
                navigation(window,name)
                assert window.shell.emergency.visibleRegion().contains(window.shell.emergency.rect().center())
                if width==1024 and name=='recorder':
                    assert window.docks['recorder'].isVisible()
                    QTest.mouseClick(window.shell.preview_toggle,Qt.MouseButton.LeftButton)
                    assert not window.docks['recorder'].isVisible() and window.shell.preview_slots['recorder'].isVisible()
                    QTest.mouseClick(window.shell.preview_toggle,Qt.MouseButton.LeftButton)
                    assert window.docks['recorder'].isVisible()
                if screenshots and width==1024 and name in ('devices','recorder'):
                    window.grab().save(str(screenshots/f'phase6-{name}-compact.png'))
        window.resize(1440,960)
        navigation(window,'settings'); window.shell.settings_panel.theme.setCurrentText('light')
        click(window.shell.settings_panel,'Apply settings')
        navigation(window,'studio');window.select_simulation(one); QTest.qWait(180)
        if screenshots: window.grab().save(str(screenshots/'phase6-light.png'))
        navigation(window,'settings'); window.shell.settings_panel.theme.setCurrentText('dark');click(window.shell.settings_panel,'Apply settings');navigation(window,'studio')
        window.resize(1024,700);QTest.qWait(160)
        if screenshots: window.grab().save(str(screenshots/'phase6-compact.png'))
        assert not native_calls
        gaps=[1000*(b-a) for a,b in zip(ticks,ticks[1:])]
        print(json.dumps({'gui_measurements':{'window_to_monaco_ms':round(startup_ms,1),'heartbeat_samples':len(ticks),'max_heartbeat_gap_ms':round(max(gaps),1),'qt_scale_factor':app.devicePixelRatio()},'checks':{key:True for key in ('demo_start','isolated_workers','recognition_inspector','pixel_insertion','recorder_conversion','recorder_replay','pause_resume','emergency_stop','independent_simulations','strict_adb_isolation','themes','responsive','failure_inspection')}}))
    finally:
        QMessageBox.warning,QMessageBox.question=warning,question
        QFileDialog.getSaveFileName=get_save
        for dialog in list(window._capture_dialogs):dialog.reject()
        for document in window.shell.documents.documents:document.saved=document.source
        window.saved_source=window.editor.source
        window.close();spin(app,lambda:window._shutdown_complete,timeout=15)
        assert not window.jobs
        assert not Path(window.simulations._temporary.name).exists()


if __name__=='__main__':main()
