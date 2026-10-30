"""Connection-generation races using spawned workers and declared mock devices."""

import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Slot

from app.automation import qt_service
from app.automation.qt_service import RuntimeService


@pytest.fixture(scope="module")
def qt_core():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class Receiver(QObject):
    def __init__(self, service):
        super().__init__()
        self.events = []
        self.snapshots = []
        service.event.connect(self.on_event)
        service.snapshot_changed.connect(self.on_snapshot)

    @Slot(dict)
    def on_event(self, event):
        self.events.append(event)

    @Slot(object)
    def on_snapshot(self, snapshot):
        self.snapshots.append(snapshot)


def spin(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("Timed out waiting for device-loss service behavior")


def test_queued_old_generation_rejected_after_reallow(qt_core, monkeypatch):
    ready = threading.Event()
    original = qt_service.RuntimeCoordinator

    def delayed_constructor(**arguments):
        ready.wait(5)
        return original(**arguments)

    monkeypatch.setattr(qt_service, "RuntimeCoordinator", delayed_constructor)
    service = RuntimeService()
    receiver = Receiver(service)
    try:
        stale = service.start("tap(1, 2)", "fixture-one", trusted=True)
        generation = service.invalidate_device("fixture-one")
        assert generation == 1
        with pytest.raises(RuntimeError, match="unavailable"):
            service.start("tap(3, 4)", "fixture-one", trusted=True)
        assert service.allow_device("fixture-one") == generation
        fresh = service.start("tap(99, 2)", "fixture-one", trusted=True)
        ready.set()
        spin(qt_core, lambda: any(e.get("state") == "completed" for e in receiver.events))
        stale_response = [e for e in receiver.events if e.get("request_id") == stale]
        assert len(stale_response) == 1
        assert stale_response[0]["event"] == "request_error"
        assert "generation changed" in stale_response[0]["message"]
        assert any(e["event"] == "request" and e.get("request_id") == fresh for e in receiver.events)
        actions = [e for e in receiver.events if e["event"] == "action"]
        assert [e["arguments"]["x"] for e in actions] == [99]
    finally:
        ready.set()
        assert service.close()


def test_device_loss_cancels_one_phone_and_never_replays(qt_core):
    service = RuntimeService(max_workers=2)
    receiver = Receiver(service)
    try:
        request_one = service.start("sleep(60)\ntap(1, 2)", "fixture-one", trusted=True)
        request_two = service.start("sleep(0.3)\ntap(99, 2)", "fixture-two", trusted=True)
        spin(qt_core, lambda: len([e for e in receiver.events if e.get("state") == "running"]) == 2)
        run_one = next(e["run_id"] for e in receiver.events if e.get("request_id") == request_one)
        run_two = next(e["run_id"] for e in receiver.events if e.get("request_id") == request_two)
        started = time.monotonic()
        service.invalidate_device("fixture-one")
        assert time.monotonic() - started < 0.1
        # Reconnection only permits new user actions; it does not rerun source.
        service.allow_device("fixture-one")
        spin(qt_core, lambda: receiver.snapshots and
             {run.run_id: run.state for run in receiver.snapshots[-1]}.get(run_one) == "cancelled" and
             {run.run_id: run.state for run in receiver.snapshots[-1]}.get(run_two) == "completed")
        actions = [e for e in receiver.events if e["event"] == "action"]
        assert [(e["serial"], e["arguments"]["x"]) for e in actions] == [("fixture-two", 99)]
        assert len([e for e in receiver.events if e["event"] == "request" and e.get("command") == "start"]) == 2
        fresh = service.start("tap(42, 2)", "fixture-one", trusted=True)
        spin(qt_core, lambda: any(e.get("request_id") == fresh and e["event"] == "request" for e in receiver.events))
        spin(qt_core, lambda: any(e["event"] == "action" and e["serial"] == "fixture-one" for e in receiver.events))
        assert any(e["event"] == "action" and e["arguments"].get("x") == 42 for e in receiver.events)
    finally:
        assert service.close()


def test_invalidation_during_spawn_never_activates_stale_source(qt_core, monkeypatch):
    spawned = threading.Event()
    release = threading.Event()
    original = qt_service.RuntimeCoordinator

    class DelayedSpawn(original):
        def start(self, *arguments, **keywords):
            run_id = super().start(*arguments, **keywords)
            if keywords["serial"] == "fixture-one":
                spawned.set()
                release.wait(5)
            return run_id

    monkeypatch.setattr(qt_service, "RuntimeCoordinator", DelayedSpawn)
    service = RuntimeService()
    receiver = Receiver(service)
    try:
        stale = service.start("tap(1, 2)", "fixture-one", trusted=True)
        spin(qt_core, spawned.is_set)
        started = time.monotonic()
        service.invalidate_device("fixture-one")
        # No lock is held across the intentionally blocked process-start path.
        assert time.monotonic() - started < 0.1
        service.allow_device("fixture-one")
        release.set()
        spin(qt_core, lambda: any(e.get("request_id") == stale for e in receiver.events))
        response = next(e for e in receiver.events if e.get("request_id") == stale)
        assert response["event"] == "request_error"
        assert "before activation" in response["message"]
        spin(qt_core, lambda: receiver.snapshots and receiver.snapshots[-1][0].exitcode is not None)
        assert not any(e["event"] == "action" for e in receiver.events)
        assert receiver.snapshots[-1][0].state == "cancelled"
        service.start("tap(99, 2)", "fixture-one", trusted=True)
        spin(qt_core, lambda: any(e["event"] == "action" for e in receiver.events))
        assert [e["arguments"]["x"] for e in receiver.events if e["event"] == "action"] == [99]
    finally:
        release.set()
        assert service.close()


def test_cancellation_event_reaches_run_while_service_busy_spawning(qt_core, monkeypatch, tmp_path):
    spawned = threading.Event()
    release = threading.Event()
    original = qt_service.RuntimeCoordinator

    class DelayedSpawn(original):
        def start(self, *arguments, **keywords):
            run_id = super().start(*arguments, **keywords)
            if keywords["serial"] == "fixture-two":
                spawned.set()
                release.wait(5)
            return run_id

    monkeypatch.setattr(qt_service, "RuntimeCoordinator", DelayedSpawn)
    service = RuntimeService(max_workers=2)
    receiver = Receiver(service)
    marker = tmp_path / "cooperatively-cancelled.txt"
    source = ("from pathlib import Path\ntry:\n    sleep(60)\nexcept Exception:\n"
              f"    Path({str(marker)!r}).write_text('cancelled', encoding='utf-8')\n")
    try:
        service.start(source, "fixture-one", trusted=True)
        spin(qt_core, lambda: any(e.get("state") == "running" for e in receiver.events))
        service.start("sleep(1)", "fixture-two", trusted=True)
        spin(qt_core, spawned.is_set)
        service.invalidate_device("fixture-one")
        # The service cannot process commands or poll while blocked above. This
        # marker proves its registered cancellation Event was signalled directly.
        spin(qt_core, marker.exists, timeout=2)
        assert marker.read_text(encoding="utf-8") == "cancelled"
    finally:
        release.set()
        assert service.close()
