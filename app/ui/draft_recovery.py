"""Native recovery-copy autosave; recovered Python remains an unapproved buffer."""
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                              QListWidget, QListWidgetItem, QMessageBox, QSpinBox,
                              QVBoxLayout)

from app.projects.drafts import DraftStore, snapshot_fingerprint
from app.settings import integer
from app.ui.components import button, label


class DraftRecoveryController(QObject):
    def __init__(self, window, data_root):
        super().__init__(window)
        self.window = window
        self.store = DraftStore(Path(data_root) / "draft-recovery")
        self.session = uuid4().hex
        self.pending = False
        self.last = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.flush)
        self._configure()
        QTimer.singleShot(750, self._notice)

    def _configure(self):
        enabled = self.window.settings.value("autosave/enabled", True, type=bool)
        seconds = integer(self.window.settings, "autosave/seconds", 30, 5, 600)
        self.timer.setInterval(seconds * 1000)
        self.timer.start() if enabled else self.timer.stop()

    def _notice(self):
        if self.window._closing:
            return
        def done(result, error):
            if error:
                self.window.log(f"Recovery snapshots unavailable: {error}")
            elif result[0] or result[1]:
                self.window.notify("Unsaved recovery copies are available. Open Projects → Recover unsaved scripts. No script was run.")
        self.window._submit(lambda: self.store.sessions(exclude=self.session), done)

    def flush(self):
        if self.pending or self.window._closing:
            return
        self.window.shell.documents.remember()
        documents = [{"key": d.key, "path": str(d.path.resolve()) if d.path else None,
                      "project": str(d.project.resolve()), "source": d.source, "saved": d.saved}
                     for d in self.window.shell.documents.documents if d.source != d.saved]
        self.pending = True
        previous = self.last
        def operation():
            fingerprint = snapshot_fingerprint(documents)
            if fingerprint != previous:
                self.store.write(self.session, documents)
            return fingerprint
        def done(fingerprint, error):
            self.pending = False
            if error:
                self.window.log(f"Recovery autosave failed: {error}")
            else:
                self.last = fingerprint
        self.window._submit(operation, done)

    def stop(self, *, clean=True):
        self.timer.stop()
        if clean:
            self.store.remove(self.session)

    def show_settings(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Autosave recovery copies")
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Save recovery copies of dirty and untitled tabs. Original Python files are never overwritten by the timer. Copies may contain private source; they stay in this user's local data directory."))
        enabled = QCheckBox("Enable automatic recovery copies")
        enabled.setChecked(self.window.settings.value("autosave/enabled", True, type=bool))
        enabled.setAccessibleName("Enable automatic recovery copies")
        layout.addWidget(enabled)
        form = QFormLayout()
        seconds = QSpinBox()
        seconds.setRange(5, 600)
        seconds.setValue(integer(self.window.settings, "autosave/seconds", 30, 5, 600))
        form.addRow("Interval (seconds)", seconds)
        layout.addLayout(form)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        layout.addWidget(actions)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.window.settings.setValue("autosave/enabled", enabled.isChecked())
            self.window.settings.setValue("autosave/seconds", seconds.value())
            self.window.settings.sync()
            self._configure()

    def show_recovery(self):
        self.window._submit(lambda: self.store.sessions(exclude=self.session), self._show_sessions)

    def _show_sessions(self, result, error):
        if error:
            self.window.notify(f"Cannot inspect recovery copies: {error}")
            return
        sessions, problems = result
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Recover unsaved scripts")
        dialog.resize(760, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Select recovery copies to restore as new unsaved tabs. Existing files and running scripts are preserved. Recovery does not grant execution approval."))
        choices = QListWidget()
        choices.setAccessibleName("Unsaved script recovery copies")
        for session in sessions:
            for entry in session["documents"]:
                item = QListWidgetItem(f"{session['updated_at']} · {entry['path'] or 'Untitled.py'}")
                item.setData(Qt.ItemDataRole.UserRole, {"session": session["session"], "updated_at": session["updated_at"], "entry": entry})
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                choices.addItem(item)
        layout.addWidget(choices)
        message = label("\n".join(problems) if problems else ("No unsaved recovery copies found." if not sessions else "Recovery copies remain available until explicitly removed or their original session closes cleanly."), "notice")
        layout.addWidget(message)
        def restore():
            restored = 0
            try:
                for index in range(choices.count()):
                    item = choices.item(index)
                    if item.checkState() != Qt.CheckState.Checked:
                        continue
                    entry = item.data(Qt.ItemDataRole.UserRole)["entry"]
                    project = Path(entry["project"])
                    if not project.is_dir():
                        raise ValueError(f"Project directory is unavailable: {project}. Restore/move that project first; its recovery copy was preserved.")
                    self.window.shell.documents.add(None, entry["source"], project)
                    self.window.saved_source = entry["saved"]
                    self.window._update_title()
                    restored += 1
                message.setText(f"Restored {restored} unsaved tab(s). Save explicitly before exporting or running. Original recovery copies remain preserved.")
                self.flush()
            except (OSError, ValueError) as problem:
                message.setText(str(problem))
        layout.addWidget(button("Restore selected as unsaved tabs", restore, primary=True))
        def discard():
            selected = {}
            for index in range(choices.count()):
                item = choices.item(index)
                if item.checkState() == Qt.CheckState.Checked:
                    record = item.data(Qt.ItemDataRole.UserRole)
                    entry = selected.setdefault(record["session"], {"updated_at": record["updated_at"], "keys": []})
                    entry["keys"].append(record["entry"]["key"])
            if not selected:
                return
            answer = QMessageBox.question(dialog, "Delete selected recovery copies",
                "Permanently delete these selected local recovery copies? Saved Python files and currently open editor tabs are preserved. Save recovered tabs before deleting their last recovery copy.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return
            def operation():
                for identity, entry in selected.items():
                    self.store.discard_documents(identity, entry["keys"], expected_updated_at=entry["updated_at"])
            def done(_, failure):
                if failure:
                    message.setText(str(failure))
                else:
                    dialog.accept()
            self.window._submit(operation, done)
        layout.addWidget(button("Delete selected recovery copies…", discard))
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()
