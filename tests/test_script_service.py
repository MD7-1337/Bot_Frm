"""Qt service pause/resume stays asynchronous and reports actual worker state."""
import time

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QTimer, Slot

from app.automation.qt_service import RuntimeService


class Receiver(QObject):
    def __init__(self, service):
        super().__init__()
        self.events = []
        self.states = []
        service.event.connect(self.on_event)
        service.snapshot_changed.connect(self.on_snapshot)

    @Slot(dict)
    def on_event(self, event):
        self.events.append(event)

    @Slot(object)
    def on_snapshot(self, states):
        self.states = list(states)


def spin(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    pytest.fail("Qt scripting service did not reach expected state")


def test_service_pause_resume_preserves_other_phone_and_stop(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    service = RuntimeService(max_workers=2)
    receiver = Receiver(service)
    timer = QTimer()
    ticks = []
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    try:
        request = service.start("sleep(60)", "fixture-one", trusted=True, project_root=tmp_path)
        service.start("sleep(.2)\ntap(11,22)", "fixture-two", trusted=True, project_root=tmp_path)
        spin(app, lambda: any(e.get("state") == "running" and e.get("serial") == "fixture-one" for e in receiver.events))
        run_id = next(e["run_id"] for e in receiver.events if e.get("request_id") == request and e["event"] == "request")
        started = time.monotonic()
        service.pause(run_id)
        assert time.monotonic() - started < .1
        spin(app, lambda: any(run.run_id == run_id and run.state == "paused" for run in receiver.states))
        spin(app, lambda: any(e.get("state") == "completed" and e.get("serial") == "fixture-two" for e in receiver.events))
        before = len(ticks)
        spin(app, lambda: len(ticks) >= before + 3)
        service.resume(run_id)
        spin(app, lambda: any(run.run_id == run_id and run.state == "running" for run in receiver.states))
        service.cancel(run_id)
        spin(app, lambda: any(run.run_id == run_id and run.exitcode is not None for run in receiver.states))
        assert any(e["event"] == "action" and e["serial"] == "fixture-two" for e in receiver.events)
        assert next(run for run in receiver.states if run.run_id == run_id).state == "cancelled"
    finally:
        timer.stop()
        assert service.close()
