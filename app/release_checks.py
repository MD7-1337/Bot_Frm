"""Actual packaged-resource, spawned-worker and Qt workbench release smoke.

This executes only this module's trusted built-in simulation source. It never
discovers Android phones or runs imported user projects.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import traceback


def simulation_smoke(root: Path, *, count: int = 1, timeout: float = 30) -> dict:
    from app.automation.runtime import RuntimeCoordinator, TERMINAL_STATES
    from app.simulation.model import SimulationManager
    from app.simulation.project import create_project, SOURCES
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError("Smoke count must be between one and four")
    start = time.perf_counter()
    manager = SimulationManager()
    events = []
    try:
        identities = [manager.create() for _ in range(count)]
        with RuntimeCoordinator(max_workers=count) as runtime:
            for identity in identities:
                project, script = create_project(root, identity.serial, "image")
                runtime.start(SOURCES["image"], identity.serial, backend="simulation", trusted=True,
                              project_root=project, script_id=str(script), simulation_config=manager.config(identity.serial))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                events.extend(runtime.poll())
                runs = runtime.snapshot()
                if len(runs) == count and all(run.state in TERMINAL_STATES for run in runs):
                    break
                time.sleep(.01)
            else:
                raise TimeoutError("Release smoke worker did not finish within its budget")
            if any(run.state != "completed" for run in runs):
                failures = [event for event in events if event.get("event") == "error"]
                raise RuntimeError(f"Release worker failed: {failures!r}")
            for identity in identities:
                if manager.client(identity.serial).state()["screen"] != "dashboard":
                    raise RuntimeError("Real template click did not change the simulation screen")
            return {"passed": True, "devices": count, "independent_pids": len({run.pid for run in runs}),
                    "elapsed_seconds": round(time.perf_counter() - start, 4),
                    "actions": "actual image matching and click changed each simulation state",
                    "android_hardware": "NOT VERIFIED"}
    finally:
        manager.close()


def gui_smoke(*, timeout_ms: int = 60000) -> dict:
    """Exercise bundled GUI, debugger, recorder, scheduler and project storage.

    Only built-in fixture code is approved. No project supplied by a user is
    loaded or trusted. Run this explicitly through --release-smoke-report.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox
    from app.projects.management import ProjectStore
    from app.tasks.store import Task, TaskStore
    from app.host_metrics import resident_bytes
    from datetime import timedelta
    from app.ui.window import StudioWindow
    application = QApplication.instance() or QApplication(["AndroidAutomationStudio release smoke"])
    application.setQuitOnLastWindowClosed(False)
    started = time.perf_counter()
    deadline = time.monotonic() + timeout_ms / 1000
    heartbeat = []
    beat = QTimer()
    beat.timeout.connect(lambda: heartbeat.append(time.perf_counter()))
    beat.start(20)
    window = StudioWindow(discover=False)
    events = []
    window.runtime.event.connect(events.append)
    window.show()

    def wait(predicate, name):
        while time.monotonic() < deadline:
            application.processEvents()
            if predicate():
                return
            time.sleep(.005)
        raise TimeoutError(f"Packaged workflow timed out: {name}; logs={window.logs.toPlainText()[-2000:]}")

    def approve(operation, title):
        acknowledged = []
        timer = QTimer()
        def accept_known_dialog():
            dialog = application.activeModalWidget()
            if dialog is not None and dialog.windowTitle() == title and not acknowledged:
                if isinstance(dialog, QMessageBox):
                    dialog.button(QMessageBox.StandardButton.Yes).click()
                elif isinstance(dialog, QDialog):
                    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
                acknowledged.append(True)
            elif time.monotonic() >= deadline and dialog is not None:
                dialog.reject()
        timer.timeout.connect(accept_known_dialog)
        timer.start(20)
        try:
            operation()
        finally:
            timer.stop()
        if not acknowledged:
            raise RuntimeError(f"Built-in smoke approval dialog not reached: {title}")

    try:
        wait(lambda: window.editor.is_ready and not window.jobs, "offline Monaco")
        startup_ms = round(1000 * (time.perf_counter() - started), 1)
        idle_rss = resident_bytes()
        window.start_demo()
        wait(lambda: window.active_simulation and window.preview.frame is not None
             and not window._demo_pending, "explicit Demo Mode")
        serial, project = window.active_simulation, window.project_root
        managed = ProjectStore.open(project)
        source = 'counter = 40\ncounter += 2\nhome()\nclick("start.png")\nprint(counter)\n'
        script = project / "scripts" / "packaged-smoke.py"
        window._atomic_write(script, source.encode())
        window.open_script_path(script)
        window.editor.set_breakpoints([2])
        approve(window.debug_script, "Approve trusted Python execution")
        wait(lambda: any(e.get("event") == "debug_stopped" and e.get("line") == 2 for e in events), "frozen debugger breakpoint")
        stopped = next(e for e in reversed(events) if e.get("event") == "debug_stopped")
        if not any(v["name"] == "counter" and v["value"] == "40" for v in stopped["locals"]):
            raise RuntimeError("Frozen debugger did not inspect the real worker variable")
        wait(lambda: window.debugger_panel.buttons["step_over"].isEnabled(), "debug controls")
        window.debugger_panel.buttons["step_over"].click()
        wait(lambda: any(e.get("event") == "debug_stopped" and e.get("line") == 3 for e in events), "frozen step over")
        wait(lambda: window.debugger_panel.buttons["continue"].isEnabled(), "continue control")
        window.debugger_panel.buttons["continue"].click()
        wait(lambda: window.run_states and window.run_states[-1].exitcode is not None, "debugger cleanup")
        if window.run_states[-1].state != "completed" or window.simulations.client(serial).state()["screen"] != "dashboard":
            raise RuntimeError("Frozen debugged image click did not complete")
        # Record acknowledged studio actions and schedule the generated Python.
        window.start_recording()
        window._key("HOME")
        wait(lambda: not window.pending_controls and bool(window.recorder.actions), "recorded Home")
        window._control(serial, lambda: window._transport(serial).tap(serial, 180, 512), recorded="tap(180, 512)")
        wait(lambda: not window.pending_controls and len(window.recorder.actions) >= 2, "recorded tap")
        window.stop_recording()
        generated = window.recorder_panel.source()
        compile(generated, "<recording>", "exec")
        recording = project / "recordings"
        recording.mkdir(exist_ok=True)
        window._atomic_write(recording / "smoke.json", window.recorder.session_json().encode())
        window._atomic_write(script, generated.encode())
        task = Task(task_id="packaged-smoke", name="Built-in packaged smoke", source=generated,
                    serial=serial, project_root=str(project), script_id=str(script), schedule="once",
                    at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(), missed="run_once")
        window.task_store.save(task)
        window.task_panel.refresh()
        window.task_panel.tasks.selectRow(0)
        approve(window.task_panel.authorize, "Approve exact task source and device")
        window.scheduler.resume()
        wait(lambda: window.task_store.history(task.task_id)
             and window.task_store.history(task.task_id)[0]["state"] == "completed", "frozen scheduled recording")
        metadata = managed.metadata
        metadata["task_definitions"] = window.task_store.export_definitions(project)
        managed.save(metadata)
        archive = project.parent / "packaged project backup.zip"
        managed.export(archive)
        restored = ProjectStore.import_archive(archive, project.parent / "restored project")
        if (restored.root / "scripts" / script.name).read_text() != generated:
            raise RuntimeError("Packaged project restore lost the generated source")
        if not (restored.root / "recordings" / "smoke.json").is_file():
            raise RuntimeError("Packaged project restore lost the recorder session")
        history_path = window.task_store.path
        active_rss = resident_bytes()
        result = {"passed": True, "monaco_ready": True, "window_visible": window.isVisible(),
                  "qt_platform": application.platformName(),
                  "checks": {key: True for key in ("demo", "recognition", "debug_breakpoint", "debug_variables",
                    "debug_step", "recorder", "scheduled_worker", "project_export_restore")},
                  "startup_ms": startup_ms, "idle_parent_rss_bytes": idle_rss,
                  "active_parent_rss_bytes": active_rss, "heartbeat_samples": len(heartbeat),
                  "max_heartbeat_gap_ms": round(max((b-a for a,b in zip(heartbeat, heartbeat[1:])), default=0)*1000, 1)}
    finally:
        beat.stop()
        for document in window.shell.documents.documents:
            document.saved = document.source
        window.saved_source = window.editor.source
        window.close()
        cleanup_deadline = time.monotonic() + 15
        while not window._shutdown_complete and time.monotonic() < cleanup_deadline:
            application.processEvents()
            time.sleep(.005)
        if not window._shutdown_complete:
            raise RuntimeError("Packaged workbench did not clean up owned resources")
    with_store = TaskStore(history_path)
    try:
        if with_store.history("packaged-smoke")[0]["state"] != "completed":
            raise RuntimeError("Packaged scheduler history did not survive reopening")
        result["checks"]["persistent_history"] = True
    finally:
        with_store.close()
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return result


def write_smoke_report(path: Path) -> int:
    """Write usable evidence even for a windowed executable with no stdout."""
    report = {"passed": False, "measured_at_utc": datetime.now(timezone.utc).isoformat(),
              "frozen": bool(getattr(sys, "frozen", False)),
              "platform": platform.platform(), "python": platform.python_version(),
              "windows_runtime": "verified by this run" if os.name == "nt" else "NOT VERIFIED",
              "physical_android": "NOT VERIFIED"}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Isolate smoke settings, and restore the caller's choice afterwards.
        previous = os.environ.get("STUDIO_CONFIG_DIR")
        previous_data = os.environ.get("STUDIO_DATA_DIR")
        with tempfile.TemporaryDirectory(prefix="studio-release-smoke-") as temporary:
            root = Path(temporary)
            os.environ["STUDIO_CONFIG_DIR"] = str(root / "settings")
            os.environ["STUDIO_DATA_DIR"] = str(root / "data")
            try:
                report["simulation"] = simulation_smoke(root)
                report["gui"] = gui_smoke()
                report["passed"] = True
            finally:
                if previous is None:
                    os.environ.pop("STUDIO_CONFIG_DIR", None)
                else:
                    os.environ["STUDIO_CONFIG_DIR"] = previous
                if previous_data is None:
                    os.environ.pop("STUDIO_DATA_DIR", None)
                else:
                    os.environ["STUDIO_DATA_DIR"] = previous_data
    except Exception:
        report["error"] = traceback.format_exc(limit=12)
    temporary_report = path.with_suffix(path.suffix + ".tmp")
    temporary_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary_report.replace(path)
    return 0 if report["passed"] else 1
