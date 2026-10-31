"""Real Monaco process loss followed by native opt-in recovery of dirty buffers."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QDialogButtonBox, QInputDialog, QPushButton, QSpinBox

from app.projects.management import ProjectStore
from app.ui.project_panel import ProjectConfigurationDialog
from app.ui.window import StudioWindow


def spin(app, predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Recovery GUI timed out")


def main(root, mode):
    root.mkdir(parents=True, exist_ok=True)
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    window = StudioWindow(discover=False)
    window.show()
    spin(application, lambda: window.editor.is_ready and not window.jobs)
    assert window.draft_recovery is not None
    if mode == "crash":
        store = ProjectStore.create(root / "project", "Crash recovery proof")
        path = store.root / "scripts/main.py"
        path.write_text("print('saved source')\n")
        window._set_project(store.root)
        window.open_script_path(path)
        window.editor.set_text("print('recovered dirty source')\n")
        window.new_script()
        window.editor.set_text("print('recovered untitled source')\n")
        window.draft_recovery.flush()
        spin(application, lambda: not window.draft_recovery.pending and not window.jobs)
        snapshot = window.draft_recovery.store.read(window.draft_recovery.session)
        assert len(snapshot["documents"]) == 2
        assert not window.run_states
        (root / "session.txt").write_text(window.draft_recovery.session)
        print(json.dumps({"actual_dirty_buffers_autosaved": True}), flush=True)
        # Deliberate abrupt termination, bypassing closeEvent/normal clean-up.
        # No automation worker or physical device is started in this probe.
        os._exit(0)
    if mode != "recover":
        raise ValueError(mode)
    path = root / "project/scripts/main.py"
    before = path.read_text()
    errors = []
    def interact():
        dialog = application.activeModalWidget()
        if not isinstance(dialog, QDialog) or dialog.windowTitle() != "Recover unsaved scripts":
            return
        timer.stop()
        try:
            button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Restore selected as unsaved tabs")
            button.click()
            assert len([d for d in window.shell.documents.documents if d.source != d.saved]) == 2
            assert any("recovered dirty source" in d.source and d.path is None for d in window.shell.documents.documents)
            assert any("recovered untitled source" in d.source and d.path is None for d in window.shell.documents.documents)
        except Exception as error:
            errors.append(error)
        dialog.accept()
    timer = QTimer()
    timer.timeout.connect(interact)
    timer.start(20)
    window.draft_recovery.show_recovery()
    spin(application, lambda: not timer.isActive() and not window.jobs)
    assert not errors, errors
    assert path.read_text() == before == "print('saved source')\n"
    assert not window.run_states and window.scheduler.paused
    # Configuration widgets persist actual presets without executing them.
    metadata = ProjectStore.open(root / "project").metadata
    dialog = ProjectConfigurationDialog(metadata, window, project_root=root / "project")
    dialog.threshold.setValue(.92)
    dialog.scales.setText(".8, 1.0")
    dialog.preprocessing.setCurrentText("edges")
    dialog._add_run("Saved", "scripts/main.py")
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    store = ProjectStore.open(root / "project")
    store.configure(*dialog.configuration)
    assert ProjectStore.open(store.root).metadata["recognition"]["threshold"] == .92
    def configure_autosave():
        modal = application.activeModalWidget()
        if isinstance(modal, QDialog) and modal.windowTitle() == "Autosave recovery copies":
            modal.findChild(QCheckBox).setChecked(False)
            modal.findChild(QSpinBox).setValue(12)
            modal.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    QTimer.singleShot(50, configure_autosave)
    window.draft_recovery.show_settings()
    assert window.settings.value("autosave/enabled", True, type=bool) is False
    assert window.settings.value("autosave/seconds", 30, type=int) == 12
    assert not window.draft_recovery.timer.isActive()
    # Delete means a confirmed reversible move; other unsaved projects survive.
    movable = ProjectStore.create(root / "move-me", "Move proof")
    (movable.root / "notes.txt").write_text("preserved project files")
    # Preserve the dirty tab's old project context before choosing another root.
    window.new_script()
    window.project_panel._adopt(movable)
    window.new_script()
    spin(application, lambda: not window.jobs)
    def confirm_trash():
        modal = application.activeModalWidget()
        if isinstance(modal, QInputDialog) and modal.windowTitle() == "Move project to trash":
            modal.setTextValue("Move proof")
            modal.accept()
    QTimer.singleShot(50, confirm_trash)
    window.project_panel.trash()
    spin(application, lambda: not window.project_panel.busy and not window.jobs)
    assert not movable.root.exists(), window.project_panel.summary.text()
    assert (window.project_root / "notes.txt").read_text() == "preserved project files"
    assert window.project_root.parent.name == ".studio-trash"
    assert any("recovered dirty source" in document.source for document in window.shell.documents.documents)
    # Preserve original crash journal until explicitly dismissed by its owner.
    original_session = (root / "session.txt").read_text()
    assert window.draft_recovery.store.read(original_session)["documents"]
    for document in window.shell.documents.documents:
        document.saved = document.source
    window.saved_source = window.editor.source
    window.close()
    spin(application, lambda: window._shutdown_complete)
    print(json.dumps({"crash_recovery_native_dialog": True, "original_files_preserved": True,
                      "recovery_did_not_execute_python": True, "project_configuration_widgets": True,
                      "autosave_configured": True, "reversible_project_delete": True}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
