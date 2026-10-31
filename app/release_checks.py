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


def gui_smoke(*, timeout_ms: int = 30000) -> dict:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.ui.window import StudioWindow
    application = QApplication.instance() or QApplication(["AndroidAutomationStudio release smoke"])
    window = StudioWindow(discover=False)
    result = {"passed": False, "monaco_ready": False, "window_visible": False}
    finished = False

    def finish(ok):
        nonlocal finished
        if finished:
            return
        finished = True
        result.update(passed=bool(ok), monaco_ready=window.editor.is_ready, window_visible=window.isVisible())
        window.close()
        # The normal close lifecycle gets time to finish its background jobs;
        # fail rather than leave a frozen smoke process indefinitely alive.
        QTimer.singleShot(15000, application.quit)

    timer = QTimer(window)
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: finish(False))
    timer.start(timeout_ms)
    window.editor.ready.connect(lambda: QTimer.singleShot(300, lambda: finish(True)))
    window.show()
    application.exec()
    if not result["passed"]:
        raise RuntimeError(f"Packaged workbench Monaco readiness failed: {result}")
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
