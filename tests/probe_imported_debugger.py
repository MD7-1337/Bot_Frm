"""Real Monaco, native stack/variables, source snapshots and spawned worker."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter, QTabWidget
from app.automation.debug_sources import snapshot_sources
from app.automation.qt_service import RuntimeService
from app.editor.widget import EditorWidget
from app.ui.debugger_panel import DebuggerPanel


def main(root):
    os.environ['STUDIO_DATA_DIR'] = str(root / 'user-data')
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    source = 'def calculate(value):\n    inside = value + 2\n    return inside\n'
    helper = root / 'helper.py'
    helper.write_text(source)
    main_path = root / 'main.py'
    main_source = 'from helper import calculate\nanswer = calculate(40)\ntap(answer, 7)\n'
    main_path.write_text(main_source)
    window = QSplitter(Qt.Orientation.Vertical)
    editor = EditorWidget()
    editor.set_document_path(helper, root)
    editor.set_text(source)
    panel = DebuggerPanel()
    window.addWidget(editor)
    window.addWidget(panel)
    window.resize(1100, 850)
    window.show()
    service = RuntimeService()
    events, navigations = [], []
    service.event.connect(events.append)
    service.event.connect(panel.on_event)
    service.snapshot_changed.connect(panel.update_runs)
    panel.command_requested.connect(lambda run, command, payload: service.debug_command(run, command, **payload))
    panel.source_requested.connect(lambda *args: navigations.append(args))

    def wait(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(5)
        raise AssertionError(events[-6:])

    try:
        wait(lambda: editor.is_ready)
        editor.set_breakpoints([2])
        wait(lambda: list((root / 'user-data' / 'breakpoints').glob('*.json')))
        service.start(main_source, 'fixture-imported-gui', trusted=True, project_root=root,
            script_id=str(main_path), debug=True,
            debug_sources=snapshot_sources(root, str(main_path), main_source),
            file_breakpoints={str(helper): [2]})
        wait(lambda: panel.buttons['step_over'].isEnabled())
        assert panel.variables.topLevelItem(0).child(0).text(0) == 'value'
        assert panel.variables.topLevelItem(0).child(0).text(1) == '40'
        QTest.mouseClick(panel.buttons['step_over'], Qt.MouseButton.LeftButton)
        wait(lambda: any(e.get('event') == 'debug_stopped' and e.get('source_path') == str(helper) and e.get('line') == 3 for e in events))
        wait(lambda: panel.buttons['continue'].isEnabled())
        editor.set_execution_line(3)
        panel.findChild(QTabWidget).setCurrentWidget(panel.stack)
        QTest.qWait(50)
        item = panel.stack.item(0)
        point = panel.stack.visualItemRect(item).center()
        # Exercise the actual native signal path; a row double-click navigates
        # using that frame's own approved-source hash, not the main script hash.
        QTest.mouseClick(panel.stack.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(panel.stack.viewport(), Qt.MouseButton.LeftButton, pos=point)
        wait(lambda: bool(navigations))
        assert navigations[-1] == (str(helper), 3, hashlib.sha256(source.encode()).hexdigest())
        QTest.mouseClick(panel.buttons['continue'], Qt.MouseButton.LeftButton)
        wait(lambda: any(e.get('state') == 'completed' for e in events))
        assert any(e.get('command') == 'tap' and e['arguments']['x'] == 42 for e in events)
        editor.shutdown()
        window.close()
        app.processEvents()
        restored = EditorWidget()
        restored.set_document_path(helper, root)
        restored.set_text(source)
        restored.show()
        wait(lambda: restored.is_ready)
        assert restored.breakpoints == [2]
        restored.shutdown()
        restored.close()
        app.processEvents()
        print(json.dumps({'imported_debugger':True, 'frame_hash_navigation':True,
                          'persistent_breakpoints':True, 'actual_worker':True}), flush=True)
    finally:
        assert service.close()
        window.close()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main(Path(sys.argv[1]))
