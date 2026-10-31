"""Project preservation workspace; filesystem operations run in the host job pool."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QMessageBox, QVBoxLayout, QWidget

from app.projects.management import ProjectStore
from app.ui.components import button, label


class ProjectPanel(QWidget):
    project_opened = Signal(str)
    source_selected = Signal(str, int)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.store = None
        self.busy = False
        self.request = 0
        self.root = None
        self._hits = []
        layout = QVBoxLayout(self)
        layout.addWidget(label("Projects", "title"))
        layout.addWidget(label("Create, preserve and search automation projects. Opening a project does not authorize or run its Python scripts."))
        self.summary = label("Open a managed project or create a new one.", "notice")
        layout.addWidget(self.summary)
        self.controls = []
        for actions in (
            (("New project…", self.create), ("Open project…", self.open), ("Rename…", self.rename), ("Save metadata", self.save)),
            (("Export ZIP…", self.export), ("Create backup…", self.backup), ("Import / restore ZIP…", self.import_archive), ("Duplicate…", self.duplicate)),
        ):
            row = QHBoxLayout()
            for text, callback in actions:
                control = button(text, callback)
                self.controls.append(control)
                row.addWidget(control)
            layout.addLayout(row)
        layout.addWidget(label("Archives include scripts, images, recordings, task definitions and settings. Known credential files, hidden files and logs are excluded. Review scripts for embedded secrets before sharing."))
        self.import_tasks_button = button("Import project task definitions…", self.import_tasks)
        self.import_tasks_button.setEnabled(getattr(window, "task_store", None) is not None)
        if getattr(window, "task_store", None) is None:
            self.import_tasks_button.setToolTip("Task persistence is unavailable. Project preservation remains available.")
        self.controls.append(self.import_tasks_button)
        layout.addWidget(self.import_tasks_button)
        search = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search project text")
        self.query.setAccessibleName("Project search text")
        self.query.returnPressed.connect(self.search)
        search.addWidget(self.query)
        search.addWidget(button("Search", self.search))
        search.addWidget(button("Check image references", self.check_assets))
        layout.addLayout(search)
        self.results = QListWidget()
        self.results.setAccessibleName("Project search and missing-image results")
        self.results.itemDoubleClicked.connect(self._open_hit)
        layout.addWidget(self.results, stretch=1)
        layout.addWidget(label("Recent projects", "eyebrow"))
        self.recent = QListWidget()
        self.recent.setMaximumHeight(130)
        self.recent.setAccessibleName("Recent managed projects")
        self.recent.itemDoubleClicked.connect(lambda item: self._open(Path(item.text())))
        layout.addWidget(self.recent)
        self._refresh_recent()

    def _refresh_recent(self):
        self.recent.clear()
        values = self.window.settings.value("projects/recent_v1", [])
        if isinstance(values, str):
            values = [values]
        if isinstance(values, (list, tuple)):
            self.recent.addItems([value for value in values[:12] if isinstance(value, str)])

    def _remember(self, root):
        existing = [self.recent.item(i).text() for i in range(self.recent.count())]
        recent = [str(root)] + [value for value in existing if value != str(root)]
        self.window.settings.setValue("projects/recent_v1", recent[:12])
        self._refresh_recent()

    def _run(self, operation, success):
        if self.busy:
            return
        self.busy = True
        for control in self.controls:
            control.setEnabled(False)
        self.summary.setText("Working…")
        def finished(value, error):
            self.busy = False
            for control in self.controls:
                control.setEnabled(True)
            self.import_tasks_button.setEnabled(getattr(self.window, "task_store", None) is not None)
            if error:
                self.summary.setText(str(error))
                self.window.log(f"Projects: {error}")
                return
            success(value)
        self.window._submit(operation, finished)

    def _adopt(self, store):
        self.store, self.root = store, store.root
        self.summary.setText(f"{store.metadata['name']} · schema {store.metadata['schema_version']} · {store.root}")
        self._remember(store.root)
        self.project_opened.emit(str(store.root))

    def set_project(self, root):
        """Synchronize host selection without creating or migrating a manifest."""
        root = Path(root)
        if self.root == root:
            return
        self.request += 1
        self.root, self.store = root, None
        self.summary.setText(f"Selected folder: {root}. Open it here to validate or migrate its manifest.")

    def _require(self):
        if self.store is None:
            self.summary.setText("Open a managed project here first. Existing image-library folders remain usable in Script Studio.")
            return False
        return True

    def create(self):
        parent = QFileDialog.getExistingDirectory(self, "Parent directory for new project")
        if not parent:
            return
        name, ok = QInputDialog.getText(self, "New project", "Project name (also used for the new folder)")
        if ok and name.strip():
            # A folder component cannot escape the explicitly chosen parent.
            if Path(name).name != name or name in (".", "..") or "/" in name or "\\" in name or ":" in name:
                self.summary.setText("Choose a project name without directory separators.")
                return
            self._run(lambda: ProjectStore.create(Path(parent) / name, name), self._adopt)

    def open(self):
        root = QFileDialog.getExistingDirectory(self, "Open project (schema 1 is backed up before migration)")
        if root:
            self._open(Path(root))

    def _open(self, root):
        self._run(lambda: ProjectStore.open(root), self._adopt)

    def rename(self):
        if not self._require():
            return
        name, ok = QInputDialog.getText(self, "Rename project", "Project display name", text=self.store.metadata["name"])
        if ok:
            store = self.store
            self._run(lambda: store.rename(name), lambda _: self._adopt(store))

    def save(self):
        if self._require():
            store = self.store
            try:
                metadata = self._snapshot_metadata(store)
            except Exception as error:
                self.summary.setText(f"Project metadata could not be prepared: {error}")
                return
            self._run(lambda: store.save(metadata), lambda _: self._adopt(store))

    def _snapshot_metadata(self, store):
        """SQLite is GUI-thread owned; copy inert task definitions before jobs."""
        metadata = store.metadata
        task_store = getattr(self.window, "task_store", None)
        if task_store is None:
            return metadata
        definitions = task_store.export_definitions(store.root)
        # An imported project may contain definitions not yet imported into the
        # local scheduler. Preserve those until the user explicitly imports them.
        if definitions:
            metadata["task_definitions"] = definitions
        return metadata

    def import_tasks(self):
        if not self._require() or self.busy:
            return
        if getattr(self.window, "task_store", None) is None:
            self.summary.setText("Task persistence is unavailable. Project archives remain usable; inspect the Task Manager error.")
            return
        definitions = self.store.metadata.get("task_definitions", [])
        if not definitions:
            self.summary.setText("This project contains no exported task definitions.")
            return
        accepted = QMessageBox.question(self, "Import project task definitions",
            f"Import {len(definitions)} task definition(s) into the local Task Manager? Each receives a new identity and starts disabled and unapproved. Review the source and target before enabling or approving execution.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if accepted != QMessageBox.StandardButton.Yes:
            return
        try:
            imported = self.window.task_store.import_definitions(definitions, self.store.root)
            self.window.task_panel.refresh()
            self.summary.setText(f"Imported {len(imported)} disabled task definition(s). Review them in Task Manager; execution requires new session approval.")
        except Exception as error:
            self.summary.setText(f"Task definitions could not be imported: {error}")

    def _archive(self, backup):
        if not self._require():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save project backup" if backup else "Export project", "", "Project ZIP (*.zip)")
        if path:
            store = self.store
            try:
                metadata = self._snapshot_metadata(store)
            except Exception as error:
                self.summary.setText(f"Project archive could not be prepared: {error}")
                return
            def preserve():
                store.save(metadata)
                return store.backup(path) if backup else store.export(path)
            self._run(preserve,
                      lambda result: self.summary.setText(f"Archive saved: {result}. Only saved files are included; save edited script tabs before exporting."))

    def export(self):
        self._archive(False)

    def backup(self):
        self._archive(True)

    def _destination(self, title):
        parent = QFileDialog.getExistingDirectory(self, title)
        if not parent:
            return None
        name, ok = QInputDialog.getText(self, title, "New destination folder name")
        if ok and name and name not in (".", "..") and Path(name).name == name and not any(char in name for char in ("/", "\\", ":")):
            return Path(parent) / name
        return None

    def import_archive(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import or restore project", "", "Project ZIP (*.zip)")
        if path and (destination := self._destination("Import into a new directory")):
            self._run(lambda: ProjectStore.import_archive(path, destination), self._adopt)

    def duplicate(self):
        if self._require() and (destination := self._destination("Duplicate into a new directory")):
            store = self.store
            self._run(lambda: store.duplicate(destination), self._adopt)

    def search(self):
        if self._require():
            store, query = self.store, self.query.text()
            def display(hits):
                self.results.clear()
                self._hits = hits
                for hit in hits:
                    self.results.addItem(f"{hit.path}:{hit.line}  {hit.text}")
                self.summary.setText(f"{len(hits)} matches in saved project files (up to 200).")
            self._run(lambda: store.search(query), display)

    def check_assets(self):
        if self._require():
            store = self.store
            def display(references):
                self.results.clear()
                self._hits = []
                self.results.addItems(references)
                self.summary.setText(f"{len(references)} missing or unsafe literal image references. Dynamically built Python paths are not evaluated.")
            self._run(store.missing_assets, display)

    def _open_hit(self, item):
        index = self.results.row(item)
        if self.store and 0 <= index < len(self._hits):
            hit = self._hits[index]
            if Path(hit.path).suffix.casefold() == ".py":
                self.source_selected.emit(str(self.store.root / hit.path), hit.line)
