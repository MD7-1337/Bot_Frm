from __future__ import annotations

import argparse
import importlib.metadata
import json
import multiprocessing
import os
from pathlib import Path
import platform
import shutil
import sys


def diagnostics() -> dict:
    from app.devices.paths import adb_executable
    from app.settings import create_store
    settings = create_store()
    import hashlib
    from app.streaming.session import SERVER_SHA256
    server = Path(os.environ.get("STUDIO_SCRCPY_SERVER") or settings.value("scrcpy_server_path", "") or Path(__file__).resolve().parents[1] / ".tools/scrcpy-server-v3.1").expanduser()
    server_verified = server.is_file() and server.stat().st_size <= 2_000_000 and hashlib.sha256(server.read_bytes()).hexdigest() == SERVER_SHA256
    from app.automation.api import API_METHOD_NAMES
    return {"phase": "phase6-recognition-simulation", "platform": platform.platform(), "python": platform.python_version(),
            "dependencies": {name: importlib.metadata.version(name) for name in
                             ("PySide6", "numpy", "opencv-python-headless", "av")},
            "adb": shutil.which(adb_executable(settings.value("adb_path", ""))),
            "scrcpy": shutil.which("scrcpy"),
            "monaco_local": (Path(__file__).resolve().parents[1] / "editor_web/vendor/vs/loader.js").is_file(),
            "scrcpy_server_version": "3.1", "scrcpy_server_verified": server_verified,
            "embedded_scrcpy": "implemented; hardware acceptance unverified",
            "automation_commands": list(API_METHOD_NAMES), "script_pause_resume": True,
            "workspaces": ["Script Studio", "Device Manager", "Visual Tools", "Recorder", "Activity & Logs", "Task Manager (planned scheduling)", "Settings"],
            "recorder": "studio controls; pre-tap evidence; explicit saved image conversion; JSON v1/v2; trusted replay",
            "simulation": "explicit opt-in; 3 stateful scenarios; separate transport; no Android hardware verification",
            "ocr": {"engine": "optional local Tesseract TSV; no downloads", "executable": shutil.which(settings.value("ocr_executable", "") or os.environ.get("STUDIO_TESSERACT") or "tesseract")},
            "failure_inspection": "typed advice and source navigation; no automatic retry; breakpoint debugger deferred",
            "connection_diagnostics": "staged ADB/query/screenshot/video checks; physical device required for final stages",
            "template_scales": "explicit 1–16 values in [0.1, 4]; default 1.0",
            "windows_release": "not built"}


def main() -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Android Automation Studio Python automation workbench")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--diagnose-connection", action="store_true", help="Run staged connection checks without opening the GUI")
    parser.add_argument("--serial", help="Exact ADB serial to diagnose; defaults to the only authorized device")
    parser.add_argument("--no-video", action="store_true", help="Skip video in connection diagnostics (NOT VERIFIED)")
    parser.add_argument("--smoke", action="store_true", help="Open real workbench, require Monaco ready, then exit")
    args = parser.parse_args()
    if args.diagnostics:
        print(json.dumps(diagnostics(), indent=2))
        return 0
    if args.diagnose_connection:
        from app.devices.adb import AdbClient
        from app.devices.paths import adb_executable
        from app.devices.diagnostics import ConnectionDiagnostics
        from app.settings import create_store
        from app.streaming.manager import StreamManager
        settings = create_store()
        adb = AdbClient(adb_executable(settings.value("adb_path", "")))
        streams = StreamManager(adb)
        if configured := os.environ.get("STUDIO_SCRCPY_SERVER") or settings.value("scrcpy_server_path", ""):
            streams.server_path = Path(configured).expanduser()
        try:
            report = ConnectionDiagnostics(adb, streams).run(args.serial, video=not args.no_video)
            print(report.text())
            return int(any(step.state == "failed" for step in report.steps))
        finally:
            streams.close(timeout=10)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDockWidget
    from app.ui.window import StudioWindow
    application = QApplication(sys.argv)
    window = StudioWindow(discover=not args.smoke)
    if args.smoke:
        def finish(ok):
            print(json.dumps({"window": True, "monaco_ready": ok, "dock_count": len(window.findChildren(QDockWidget))}), flush=True)
            window.close()
            # Let asynchronous worker/service cleanup complete through closeEvent.
            if not ok:
                application.exit(1)
        window.editor.ready.connect(lambda: QTimer.singleShot(500, lambda: finish(True)))
        QTimer.singleShot(20000, lambda: finish(False))
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
