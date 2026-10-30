"""Actual Monaco/Qt/worker execution with explicit fixture-device injection."""
from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMessageBox

from app.automation.qt_service import RuntimeService
from app.ui import window as module
from probe_device_workbench import FixtureAdb, FixtureStreams, spin


def main():
    directory = Path(sys.argv[1])
    (directory / "images").mkdir()
    scripts = directory / "scripts"
    scripts.mkdir()
    fixture = FixtureAdb("explicit-fixture")
    frame_path = directory / "frame.png"
    frame_path.write_bytes(fixture.png)
    assert fixture.image.copy(13, 24, 17, 19).save(str(directory / "images/target.png"), "PNG")

    class FixtureRuntimeService(RuntimeService):
        def start(self, source, serial, **kwargs):
            # The actual GUI always requests ADB. Only this test substitutes
            # deterministic PNG fixtures while keeping real spawned workers.
            assert kwargs.pop("backend") == "adb"
            return super().start(source, serial, backend="mock", mock_config={"frame_paths": [str(frame_path)]}, **kwargs)

    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    module.AdbClient = FixtureAdb
    module.StreamManager = FixtureStreams
    module.RuntimeService = FixtureRuntimeService
    original_warning = QMessageBox.warning
    QMessageBox.warning = lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    window = module.StudioWindow(discover=False)
    window._set_project(directory)
    window.preview_timer.stop()
    window.stream_timer.stop()
    window.show()
    events = []
    window.runtime.event.connect(events.append)
    try:
        spin(application, lambda: window.editor.is_ready)
        window.refresh_devices()
        spin(application, lambda: window.devices.count() == 2 and not window.jobs)
        window.devices.item(0).setSelected(True)
        window.devices.item(1).setSelected(True)
        source = '''print(device.serial)
target = waitImage(Pattern("target.png").similar(0.99), timeout=1)
click(target)
for step in range(50):
    sleep(0.1)
'''
        window.editor.set_text(source)
        # Make this exact source snapshot the editor's real Monaco model too.
        source_observed = []
        window.editor.document_changed.connect(source_observed.append)
        spin(application, lambda: source in source_observed)
        window.run_selected_scripts()
        spin(application, lambda: len([event for event in events if event.get("command") == "tap"]) == 2)
        spin(application, lambda: len(window.run_states) == 2 and len(window.execution_panel.rows) == 2)
        taps = [event for event in events if event.get("command") == "tap"]
        assert {event["serial"] for event in taps} == {"fixture-one", "fixture-two"}
        assert all(event["arguments"] == {"x": 21, "y": 33} for event in taps)
        assert len({run.pid for run in window.run_states}) == 2
        first = window.run_states[0]
        second = window.run_states[1]
        window.execution_panel.table.selectRow(window.execution_panel.rows[first.run_id])
        actions = {action.text(): action for action in window.findChildren(QAction)}
        actions["Pause run"].trigger()
        spin(application, lambda: any(run.run_id == first.run_id and run.state == "paused" for run in window.run_states))
        assert next(run for run in window.run_states if run.run_id == second.run_id).state == "running"
        spin(application, lambda: first.run_id in window._run_lines)
        window._show_execution_line()
        line_verified = []
        window.editor.page.runJavaScript("window.studio.executionLine !== null", line_verified.append)
        spin(application, lambda: bool(line_verified))
        assert line_verified[0], "Actual execution line was not decorated in Monaco"
        # Editing a running source must clear its stale line rather than label
        # an unrelated line as the worker's current statement.
        window.editor.set_text("# changed\n" + source)
        spin(application, lambda: window.editor.source == "# changed\n" + source)
        window._show_execution_line()
        cleared = []
        window.editor.page.runJavaScript("window.studio.executionLine === null", cleared.append)
        spin(application, lambda: bool(cleared))
        assert cleared[0]
        actions["Resume run"].trigger()
        spin(application, lambda: any(run.run_id == first.run_id and run.state == "running" for run in window.run_states))
        actions["Stop run"].trigger()
        spin(application, lambda: any(run.run_id == first.run_id and run.state == "cancelled" and run.exitcode is not None for run in window.run_states))
        assert next(run for run in window.run_states if run.run_id == second.run_id).state == "running"
        window.emergency_stop()
        spin(application, lambda: all(run.exitcode is not None for run in window.run_states))
        spin(application, lambda: window.reset_stop_action.isEnabled())
        window.reset_emergency_stop()
        spin(application, lambda: not window._emergency_latched)

        # Different source files remain independent. One missing asset becomes
        # a typed script failure, while the second phone still finishes its tap.
        failing = scripts / "one.py"
        failing.write_text('click("missing.png")\n', encoding="utf-8")
        healthy = scripts / "two.py"
        healthy.write_text('assert device.serial == "fixture-two"\nclick("target.png")\nprint("second completed")\n', encoding="utf-8")
        window.assignments = {"fixture-one": failing, "fixture-two": healthy}
        window.devices.item(0).setSelected(True)
        window.devices.item(1).setSelected(True)
        window.run_assigned_scripts()
        spin(application, lambda: len(window.run_states) == 4 and all(run.exitcode is not None for run in window.run_states))
        final = {run.serial: run for run in window.run_states[-2:]}
        assert final["fixture-one"].state == "failed"
        assert final["fixture-two"].state == "completed"
        error = next(event for event in events if event.get("run_id") == final["fixture-one"].run_id and event["event"] == "error")
        assert error["error_type"] == "AssetNotFound" and error["source_line"] == 1
        assert "one.py" in error["traceback"]
        assert "AssetNotFound" in window.logs.toPlainText()
        assert "second completed" in window.logs.toPlainText()
        assert window.execution_panel.errors[final["fixture-one"].run_id].startswith("AssetNotFound")
        window.saved_source = window.editor.source
        window.close()
        spin(application, lambda: window._shutdown_complete)
        assert window.runtime.close(timeout=0)
        print(json.dumps({key: True for key in ("shared", "assigned", "pause_resume", "stop", "errors", "execution_line", "cleanup")}))
    finally:
        QMessageBox.warning = original_warning
        if not window._shutdown_complete:
            window.saved_source = window.editor.source
            window.close()
            spin(application, lambda: window._shutdown_complete)


if __name__ == "__main__":
    main()
