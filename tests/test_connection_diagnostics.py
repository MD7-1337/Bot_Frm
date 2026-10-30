"""Staged workflow fixtures are not Android hardware acceptance."""
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.devices.adb import AdbClient, AdbError, DeviceInfo
from app.devices.registry import DeviceRegistry
from app.devices.diagnostics import ConnectionDiagnostics, DiagnosticReport, DiagnosticStep
from test_devices import png_image, patch_run


class DiagnosticAdb:
    executable = "fixture-adb"
    def __init__(self, fail=None, listing=None):
        self.fail = fail
        self.listing = listing if listing is not None else "List of devices attached\nUSB-SECRET device model:Fixture\n"
    def _check(self, stage):
        if self.fail == stage:
            raise AdbError(f"fixture {stage} failure for USB-SECRET")
    def version(self):
        self._check("version")
        return "fixture ADB"
    def start_server(self):
        self._check("server")
    def device_listing(self):
        self._check("discovery")
        return self.listing
    def state(self, serial):
        self._check("query")
        assert serial == "USB-SECRET"
        return "device"
    def android_version(self, serial):
        return "fixture-14"
    def screenshot(self, serial):
        self._check("screenshot")
        return png_image()


class DiagnosticStreams:
    def __init__(self, fail=None, existing=False):
        self.fail, self.existing = fail, existing
        self.started = []
        self.stopped = []
    def status(self, serial):
        return SimpleNamespace(state="streaming" if self.existing else "failed" if self.started and self.fail else "starting" if self.started else "stopped", error=self.fail)
    def start(self, serial):
        self.started.append(serial)
    def latest(self, serial):
        if self.fail:
            return None
        return SimpleNamespace(serial=serial, width=2, height=3, source_width=2, source_height=3, captured_at=time.monotonic())
    def stop(self, serial):
        self.stopped.append(serial)


@pytest.fixture(autouse=True)
def executable(monkeypatch):
    monkeypatch.setattr("app.devices.diagnostics.shutil.which", lambda path: "/fixture/adb")


def test_every_stage_and_owned_video_cleanup():
    progress = []
    streams = DiagnosticStreams()
    report = ConnectionDiagnostics(DiagnosticAdb(), streams, progress=progress.append).run("USB-SECRET")
    assert len(report.steps) == 8 and all(step.state == "passed" for step in report.steps)
    assert streams.started == streams.stopped == ["USB-SECRET"]
    assert "USB-SECRET" not in report.text()
    assert "USB-SECRET" in report.text(False)
    assert "Decoded original-resolution screenshot: 2 × 3" in report.text()
    assert sum(step.state == "running" for step in progress) == 8


@pytest.mark.parametrize("stage", ["version", "server", "discovery", "query", "screenshot", "video"])
def test_failure_stops_later_checks_with_advice(stage):
    streams = DiagnosticStreams(fail="fixture video failure" if stage == "video" else None)
    report = ConnectionDiagnostics(DiagnosticAdb(stage), streams).run()
    failed = next(step for step in report.steps if step.state == "failed")
    assert failed.key == stage and failed.advice
    index = report.steps.index(failed)
    assert all(step.state == "not verified" for step in report.steps[index + 1:])
    if stage == "video":
        assert streams.stopped == ["USB-SECRET"]


def test_missing_binary_cannot_report_server_or_device_success(monkeypatch):
    monkeypatch.setattr("app.devices.diagnostics.shutil.which", lambda _: None)
    adb = DiagnosticAdb()
    adb.version = Mock()
    report = ConnectionDiagnostics(adb, DiagnosticStreams()).run()
    assert report.steps[0].state == "failed"
    assert all(step.state == "not verified" for step in report.steps[1:])
    adb.version.assert_not_called()


@pytest.mark.parametrize("listing,selected,detail", [
    ("List of devices attached\n", None, "No device detected"),
    ("List of devices attached\n???????????? no permissions (missing udev rules)\n", None, "no permissions"),
    ("List of devices attached\nUSB-SECRET unauthorized\n", "USB-SECRET", "unauthorized"),
    ("List of devices attached\nUSB-SECRET offline\n", "USB-SECRET", "offline"),
    ("List of devices attached\nUSB-SECRET device\n", "missing-phone", "not detected"),
    ("List of devices attached\nUSB-SECRET device\nUSB-two device\n", None, "Select exactly one"),
])
def test_no_phone_unavailable_and_ambiguous_selection_are_actionable(listing, selected, detail):
    report = ConnectionDiagnostics(DiagnosticAdb(listing=listing), DiagnosticStreams()).run(selected)
    assert detail in report.steps[4].detail
    assert report.steps[4].state == "failed"
    assert "NOT VERIFIED" in report.text()


def test_existing_video_is_observed_without_stopping_it():
    streams = DiagnosticStreams(existing=True)
    report = ConnectionDiagnostics(DiagnosticAdb(), streams).run()
    assert report.steps[-1].state == "passed"
    assert not streams.started and not streams.stopped


def test_disabled_video_is_not_verified():
    streams = DiagnosticStreams()
    report = ConnectionDiagnostics(DiagnosticAdb(), streams).run(video=False)
    assert report.steps[-1].state == "not verified" and not streams.started


def test_cancelled_workflow_never_dispatches_and_video_cancellation_cleans_up():
    cancel = threading.Event()
    cancel.set()
    report = ConnectionDiagnostics(DiagnosticAdb(), DiagnosticStreams(), cancel=cancel).run()
    assert all(step.state == "not verified" for step in report.steps)
    streams = DiagnosticStreams()
    original = streams.latest
    def cancelled_frame(serial):
        cancel.set()
        return None
    streams.latest = cancelled_frame
    cancel.clear()
    report = ConnectionDiagnostics(DiagnosticAdb(), streams, cancel=cancel).run()
    assert report.steps[-1].state == "failed"
    assert streams.stopped == ["USB-SECRET"]


def test_report_redacts_serials_pairing_code_and_home():
    report = DiagnosticReport(str(Path.home() / "adb"), serials=["SECRET"])
    report.steps.append(DiagnosticStep("query", "Query", "failed", "SECRET code=123456"))
    assert "SECRET" not in report.text() and "123456" not in report.text()
    assert str(Path.home()) not in report.text()


def test_unreadable_usb_serial_is_visible_but_never_routable(monkeypatch):
    listing = b"List of devices attached\n???????????? no permissions (missing udev rules)\n???????????? no permissions\n"
    run = patch_run(monkeypatch, listing)
    devices = AdbClient().devices()
    assert devices == [DeviceInfo("????????????", "no permissions")]
    registry = DeviceRegistry()
    assert registry.update(devices)[0].available is False
    assert registry.mark_unknown()[0].state == "unknown"
    assert registry.update([])[0].state == "disconnected"
    run.reset_mock()
    with pytest.raises(ValueError):
        AdbClient().tap("????????????", 1, 2)
    run.assert_not_called()
    with pytest.raises(ValueError):
        registry.update([DeviceInfo("????????????", "device")])
