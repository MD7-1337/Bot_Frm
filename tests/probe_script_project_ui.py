"""Qt project-context regression with an explicit presentation-only editor stub."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QFileDialog

from app.projects.library import AssetLibrary
from app.ui import window as module
from probe_ui_safety import TestEditor, spin


def main():
    project = Path(sys.argv[1])
    (project / "images").mkdir()
    (project / "images/target.png").write_bytes(b"resolver-only-fixture")
    (project / "tasks").mkdir()
    script = project / "tasks/daily.py"
    script.write_text('click("target.png")\n', encoding="utf-8")
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    module.EditorWidget = TestEditor
    window = module.StudioWindow(discover=False)
    window.preview_timer.stop()
    window.stream_timer.stop()
    window._set_project(project)
    original_open = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = lambda *args, **kwargs: (str(script), "Python (*.py)")
    try:
        window.open_script()
    finally:
        QFileDialog.getOpenFileName = original_open
    assert window.path == script and window.project_root == project
    assert window.editor.project_root == project
    assert AssetLibrary(window.project_root, script.parent).resolve("target.png") == project / "images/target.png"

    # A project validation failure after an atomic source write is handled,
    # logged and cannot escape a Qt Save/close callback.
    original_set = window.editor.set_project_root
    def invalid_library(*args, **kwargs):
        raise ValueError("explicit invalid image-library fixture")
    window.editor.set_project_root = invalid_library
    window.editor.source = 'print("saved source")\n'
    assert window.save_script() is False
    assert script.read_text(encoding="utf-8") == window.editor.source
    assert "invalid image-library" in window.logs.toPlainText()
    assert window.project_root == project
    window.editor.set_project_root = original_set
    window.saved_source = window.editor.source
    window.close()
    spin(application, lambda: window._shutdown_complete)
    print(json.dumps({"project": True, "save_error": True, "cleanup": True}))


if __name__ == "__main__":
    main()
