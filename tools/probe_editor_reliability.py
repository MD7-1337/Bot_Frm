"""Real WebEngine startup regressions; invoked by opt-in GUI tests."""
from pathlib import Path
import json
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.editor import widget as editor_module


def main():
    root, mode = Path(sys.argv[1]), sys.argv[2]
    if mode != "normal":
        copied = root / "editor_web"
        shutil.copytree(editor_module.EDITOR_ROOT, copied)
        loader = copied / "vendor/vs/loader.js"
        if mode == "missing":
            loader.unlink()
        else:
            loader.write_bytes(b"x" * loader.stat().st_size)
        editor_module.EDITOR_ROOT = copied
    app = QApplication([])
    editor = editor_module.EditorWidget()
    editor.resize(800, 600)
    editor.show()
    outcome = {"verified": False}

    def finish(ok):
        outcome["verified"] = bool(ok)
        print(json.dumps(outcome), flush=True)
        editor.shutdown()
        editor.close()
        app.exit(0 if ok else 1)

    if mode != "normal":
        def check_failed():
            failed = not editor.is_ready and editor.status.isVisible() and "fetch_monaco.py" in editor.status.text()
            editor._on_ready()  # A late WebChannel ready cannot undo initialization failure.
            finish(failed and not editor.is_ready)
        QTimer.singleShot(50, check_failed)
    else:
        def ready():
            editor.set_document_key("one")
            editor.set_text("x = 1\ny = 2\nz = 3\n")
            editor.set_breakpoints([2])
            def verify():
                editor.page.runJavaScript("JSON.stringify(window.studio.breakpoints)", lambda raw: switch(raw))
            def switch(raw):
                if json.loads(raw) != [2]:
                    finish(False)
                    return
                editor.set_document_key("two")
                editor.set_text("print('another script')\n")
                editor.set_document_key("one")
                editor.set_text("x = 1\ny = 2\nz = 3\n")
                QTimer.singleShot(50, lambda: editor.page.runJavaScript("JSON.stringify(window.studio.breakpoints)", lambda raw: finish(editor.is_ready and json.loads(raw) == [2])))
            QTimer.singleShot(100, verify)
        editor.ready.connect(ready)
    QTimer.singleShot(20000, lambda: finish(False))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
