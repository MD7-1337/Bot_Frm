"""Real Monaco + ScriptTabs source identity; host facade has no device runtime."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from app.editor.widget import EditorWidget
from app.ui.script_studio import ScriptTabs


def spin(application, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Monaco/tab integration did not settle")


class Host:
    def __init__(self, root):
        self.project_root = root
        self.editor = EditorWidget()
        self.path = None
        self.saved_source = ""

    def _set_project(self, root):
        self.project_root = root
        self.editor.set_project_root(root)

    def _update_title(self):
        self.tabs.remember()

    def _confirm_discard(self):
        return True

    def log(self, message):
        raise AssertionError(message)


def main(root):
    application = QApplication([])
    host = Host(root)
    host.tabs = ScriptTabs(host)
    host.tabs.resize(900, 650)
    host.tabs.show()
    spin(application, lambda: host.editor.is_ready)

    def js(expression):
        output = []
        host.editor.page.runJavaScript(expression, output.append)
        spin(application, lambda: bool(output))
        return output[0]

    def check_breakpoints(lines):
        spin(application, lambda: host.editor.breakpoints == lines and
             json.loads(js("JSON.stringify(window.studio.breakpoints)")) == lines)

    source = "x = 0\ny = 1\nz = 2\n"
    first, second = root / "one.py", root / "two.py"
    first.write_text(source)
    second.write_text(source)
    host.tabs.add(first, source, root)
    host.editor.set_breakpoints([2])
    check_breakpoints([2])
    first_key = host.tabs.documents[0].key
    host.tabs.add(second, source, root)
    check_breakpoints([])
    host.editor.set_breakpoints([3])
    check_breakpoints([3])
    assert host.tabs.documents[0].key != host.tabs.documents[1].key
    host.tabs.bar.setCurrentIndex(0)
    check_breakpoints([2])
    # Save As changes the path, while the host-owned document key stays stable.
    host.path = root / "renamed.py"
    host.tabs.remember()
    assert host.tabs.documents[0].key == first_key
    host.tabs.bar.setCurrentIndex(1)
    check_breakpoints([3])
    host.tabs.bar.setCurrentIndex(0)
    check_breakpoints([2])
    host.tabs.close_document(0)
    check_breakpoints([3])
    host.tabs.close_document(0)
    check_breakpoints([])
    print(json.dumps({"tab_breakpoints": True}), flush=True)
    host.editor.shutdown()
    host.tabs.close()
    application.processEvents()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
