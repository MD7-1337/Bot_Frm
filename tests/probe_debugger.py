"""Real Qt debugger panel + asynchronous service + spawned worker journey."""
from pathlib import Path
import json
import multiprocessing
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.automation.qt_service import RuntimeService
from app.ui.debugger_panel import DebuggerPanel


def main():
    app = QApplication([])
    panel = DebuggerPanel()
    panel.resize(900, 500)
    panel.show()
    service = RuntimeService()
    events = []
    service.event.connect(events.append)
    service.event.connect(panel.on_event)
    service.snapshot_changed.connect(panel.update_runs)
    panel.command_requested.connect(lambda run, command, payload: service.debug_command(run, command, **payload))
    panel.stop_requested.connect(service.cancel)

    def wait(predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(5)
        raise AssertionError(events[-8:])

    try:
        panel.set_breakpoints([2], "first-document")
        panel.breakpoints.item(0).setCheckState(Qt.CheckState.Unchecked)
        panel.set_breakpoints([], "second-document")
        assert panel.breakpoints.count() == 0
        panel.set_breakpoints([], "first-document")
        assert panel.breakpoints.count() == 1
        assert panel.breakpoints.item(0).checkState() == Qt.CheckState.Unchecked
        panel.set_breakpoints([2], "first-document")
        service.start("value = 7\ntap(value, 9)\nprint('done')\n", "fixture-debug-ui",
                      trusted=True, project_root=Path(sys.argv[1]), debug=True, breakpoints=[2])
        wait(lambda: panel.buttons["step_over"].isEnabled())
        assert panel.variables.topLevelItem(0).child(0).text(0) == "value"
        assert panel.variables.topLevelItem(0).child(0).text(1) == "7"
        QTest.mouseClick(panel.buttons["step_over"], Qt.MouseButton.LeftButton)
        wait(lambda: any(event["event"] == "debug_stopped" and event["line"] == 3 for event in events))
        wait(lambda: panel.buttons["continue"].isEnabled())
        QTest.mouseClick(panel.buttons["continue"], Qt.MouseButton.LeftButton)
        wait(lambda: any(event.get("state") == "completed" for event in events))
        assert any(event.get("command") == "tap" and event["arguments"] == {"x": 7, "y": 9} for event in events)
        assert "done" in panel.output.toPlainText()
        assert not panel.buttons["step_into"].isEnabled()
        print(json.dumps({"debugger_panel": True, "actual_worker": True,
                          "variables": True, "step_over": True, "continue": True}), flush=True)
    finally:
        assert service.close()
        panel.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
