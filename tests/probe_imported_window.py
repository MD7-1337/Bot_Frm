"""Workbench source navigation refuses changed imported files and dirty tabs."""
import json
import multiprocessing
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget
from app.ui.window import StudioWindow
from probe_alpha_completion import DialogDriver, spin
from probe_alpha_ux import click, navigation


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialogs = DialogDriver(app)
    window = StudioWindow(discover=False)
    window.resize(1440, 950)
    window.show()
    spin(app, lambda: window.editor.is_ready and not window.jobs)
    click(window.shell.welcome, 'Start Demo Session')
    spin(app, lambda: window.active_simulation and not window._demo_pending)
    root = window.project_root
    helper = root / 'scripts' / 'helper.py'
    helper_source = 'def calculate(value):\n    inside = value + 2\n    return inside\n'
    helper.write_text(helper_source)
    main_path = root / 'scripts' / 'imported_main.py'
    main_source = 'from helper import calculate\nanswer = calculate(40)\nprint(answer)\n'
    main_path.write_text(main_source)
    window.editor.breakpoint_store.save(helper, root, helper_source, [2])
    window.open_script_path(main_path)
    QTest.qWait(80)
    navigation(window, 'debugger')
    dialogs.trust_python()
    click(window.debugger_panel, 'Debug trusted script…')
    panel = window.debugger_panel
    spin(app, lambda: bool(panel.sessions) and panel.buttons['continue'].isEnabled())
    run = panel.selected_run()
    event = panel.sessions[run]['stop']
    assert event['source_path'] == str(helper) and event['line'] == 2

    def navigate_helper():
        panel.findChild(QTabWidget).setCurrentWidget(panel.stack)
        QTest.qWait(30)
        row = panel.stack.item(0)
        point = panel.stack.visualItemRect(row).center()
        QTest.mouseClick(panel.stack.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(panel.stack.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(60)

    try:
        navigate_helper()
        spin(app, lambda: window.path == helper and window.editor.source == helper_source)
        assert window.editor.execution_line == 2
        window.open_script_path(main_path)
        navigation(window, 'debugger')
        helper.write_text('# later disk edit\n')
        navigate_helper()
        assert window.path == main_path and window.editor.source == main_source
        assert 'Current edits preserved' in window.shell.notification.text()
        helper.write_text(helper_source)
        window.open_script_path(helper)
        window.editor.set_text('# unsaved imported source edit\n')
        QTest.qWait(80)
        window.open_script_path(main_path)
        navigation(window, 'debugger')
        navigate_helper()
        assert window.path == main_path and window.editor.source == main_source
        assert any(d.path == helper and d.source == '# unsaved imported source edit\n'
                   for d in window.shell.documents.documents)
        assert 'Current edits preserved' in window.shell.notification.text()
        QTest.mouseClick(panel.buttons['stop'], Qt.MouseButton.LeftButton)
        spin(app, lambda: any(r.run_id == run and r.exitcode is not None for r in window.run_states))
        assert next(r for r in window.run_states if r.run_id == run).state == 'cancelled'
        assert dialogs.error is None
        print(json.dumps({'imported_window_navigation':True, 'stale_disk_refused':True,
                          'dirty_tab_preserved':True, 'paused_worker_stop':True}), flush=True)
    finally:
        for document in window.shell.documents.documents:
            document.saved = document.source
        window.saved_source = window.editor.source
        window.close()
        spin(app, lambda: window._shutdown_complete)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
