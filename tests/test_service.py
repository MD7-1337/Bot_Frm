"""Qt Core integration with real spawned workers and explicit mock adapters."""

import time
import queue
import threading

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QThread, QTimer, Slot

from app.automation.qt_service import RuntimeService
from app.automation import qt_service


@pytest.fixture(scope="module")
def qt_core():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.events = []
        self.snapshots = []
        self.signal_threads = []

    @Slot(dict)
    def on_event(self, event):
        self.signal_threads.append(QThread.currentThread())
        self.events.append(event)

    @Slot(object)
    def on_snapshot(self, value):
        self.snapshots.append(value)


def spin(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("Timed out waiting for Qt runtime service events")


def test_service_runs_two_assignments_and_delivers_on_qt_thread(qt_core):
    service = RuntimeService(max_workers=2)
    receiver = Receiver()
    service.event.connect(receiver.on_event)
    service.snapshot_changed.connect(receiver.on_snapshot)
    try:
        requests = {service.start("tap(11, 22)", "fixture-one", trusted=True),
                    service.start("tap(33, 44)", "fixture-two", trusted=True)}
        spin(qt_core, lambda: len([e for e in receiver.events if e.get("state") == "completed"]) == 2)
        acknowledgments = [e for e in receiver.events if e["event"] == "request"]
        assert {e["request_id"] for e in acknowledgments} == requests
        assert len({e["run_id"] for e in acknowledgments}) == 2
        taps = [e for e in receiver.events if e["event"] == "action"]
        assert {(e["serial"], e["arguments"]["x"]) for e in taps} == {("fixture-one", 11), ("fixture-two", 33)}
        assert all(e["backend"] == "mock" for e in taps)
        assert all(thread == qt_core.thread() for thread in receiver.signal_threads)
        assert receiver.snapshots
    finally:
        assert service.close()


def test_async_cancel_keeps_qt_timer_responsive(qt_core):
    service = RuntimeService()
    receiver = Receiver()
    service.event.connect(receiver.on_event)
    ticks = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    try:
        service.start("while True: pass", "fixture-one", trusted=True)
        spin(qt_core, lambda: any(e.get("state") == "running" for e in receiver.events))
        run_id = next(e["run_id"] for e in receiver.events if e["event"] == "request")
        started = time.monotonic()
        request_id = service.cancel(run_id, grace=0.25)
        assert time.monotonic() - started < 0.1
        before = len(ticks)
        spin(qt_core, lambda: any(e.get("request_id") == request_id for e in receiver.events))
        assert len(ticks) - before >= 3
        assert any(e["event"] == "request" and e["request_id"] == request_id for e in receiver.events)
    finally:
        timer.stop()
        assert service.close()


def test_emergency_latches_start_until_reset(qt_core):
    service = RuntimeService()
    receiver = Receiver()
    service.event.connect(receiver.on_event)
    try:
        service.start("sleep(60)", "fixture-one", trusted=True)
        spin(qt_core, lambda: any(e.get("state") == "running" for e in receiver.events))
        service.emergency_stop()
        with pytest.raises(RuntimeError, match="latched"):
            service.start("pass", "fixture-two", trusted=True)
        spin(qt_core, lambda: any(e["event"] == "emergency_stopped" for e in receiver.events))
        request_id = service.reset_emergency_stop()
        spin(qt_core, lambda: any(e.get("request_id") == request_id for e in receiver.events))
        service.start("tap(1, 2)", "fixture-one", trusted=True)
        spin(qt_core, lambda: any(e.get("state") == "completed" for e in receiver.events))
    finally:
        assert service.close()


def test_service_reports_trust_errors_and_closed_submission(qt_core):
    service = RuntimeService()
    receiver = Receiver()
    service.event.connect(receiver.on_event)
    try:
        request_id = service.start("pass", "fixture-one")
        spin(qt_core, lambda: any(e.get("request_id") == request_id for e in receiver.events))
        error = next(e for e in receiver.events if e.get("request_id") == request_id)
        assert error["event"] == "request_error"
        assert "TrustRequiredError" in error["message"]
    finally:
        assert service.close()
    with pytest.raises(RuntimeError, match="closed"):
        service.start("pass", "fixture-one", trusted=True)
    assert service.close(timeout=0)


def test_submission_queue_and_shutdown_wait_are_bounded(qt_core, monkeypatch):
    gate = threading.Event()
    coordinator_class = qt_service.RuntimeCoordinator

    def delayed_constructor(**arguments):
        gate.wait(5)
        return coordinator_class(**arguments)

    monkeypatch.setattr(qt_service, "RuntimeCoordinator", delayed_constructor)
    service = RuntimeService(queue_size=1)
    try:
        service.start("pass", "fixture-one", trusted=True)
        with pytest.raises(queue.Full):
            service.start("pass", "fixture-two", trusted=True)
        started = time.monotonic()
        assert not service.close(timeout=0.01)
        assert time.monotonic() - started < 0.2
    finally:
        gate.set()
        assert service.close()
