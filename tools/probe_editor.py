"""Exercise real Monaco <-> WebChannel traffic. Exit nonzero on failure.

Use normal desktop Qt, or the documented headless test environment on Linux.
No application scripts are executed by this probe.
"""
from __future__ import annotations

import json
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.editor.widget import EditorWidget


def main() -> int:
    application = QApplication(sys.argv)
    widget = EditorWidget()
    widget.resize(900, 600)
    state = {"ready": False, "roundtrip": False, "syntax": False, "insertion": False}
    source = 'tap(12, 34)\nprint("Unicode: téléphone 📱")\n'

    def finish():
        print(json.dumps(state), flush=True)
        widget.shutdown()
        widget.close()
        application.exit(0 if all(state.values()) else 1)

    def check_markers(raw):
        state["syntax"] = bool(raw and "SyntaxError" not in str(raw) and "invalid syntax" in str(raw))
        finish()

    def check_insert(value):
        state["insertion"] = value == source + "home()\n"
        widget.set_text("if True print('broken')\n")
        QTimer.singleShot(1000, lambda: widget.page.runJavaScript(
            "JSON.stringify(monaco.editor.getModelMarkers({owner:'python-syntax'}).map(m => m.message))", check_markers))

    def on_change(text):
        if state["ready"] and not state["roundtrip"] and text == source:
            state["roundtrip"] = True
            widget.page.runJavaScript("window.studio.editor.setPosition({lineNumber:3,column:1})")
            widget.insert("home()\n")
            QTimer.singleShot(300, lambda: widget.page.runJavaScript("window.studio.getText()", check_insert))

    def on_ready():
        state["ready"] = True
        widget.set_text(source)

    widget.ready.connect(on_ready)
    widget.document_changed.connect(on_change)
    widget.error.connect(lambda message: print("EDITOR ERROR:", message, file=sys.stderr, flush=True))
    QTimer.singleShot(20000, finish)
    widget.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
