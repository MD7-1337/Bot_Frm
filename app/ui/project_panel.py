"""Project preservation workspace; filesystem operations run in the host job pool."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                              QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLineEdit,
                              QListWidget, QMenu, QMessageBox, QSpinBox, QTableWidget,
                              QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from app.projects.management import ProjectStore, validate_configuration
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
        configuration = QHBoxLayout()
        configuration.addWidget(button("Configure project…", self.configure))
        configuration.addWidget(button("Open run preset…", self.open_run))
        configuration.addWidget(button("Insert recognition preset…", self.insert_recognition))
        safety = button("Recovery & safety…", lambda: None)
        menu = QMenu(safety)
        menu.addAction("Autosave recovery settings…", lambda: self._draft_action("show_settings"))
        menu.addAction("Recover unsaved scripts…", lambda: self._draft_action("show_recovery"))
        menu.addAction("Recover project metadata…", self.recover_metadata)
        menu.addSeparator()
        menu.addAction("Move project to trash…", self.trash)
        safety.setMenu(menu)
        configuration.addWidget(safety)
        layout.addLayout(configuration)
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

    def _draft_action(self, method):
        controller = getattr(self.window, "draft_recovery", None)
        if controller is None:
            self.summary.setText("Recovery copies are unavailable. Inspect local storage diagnostics.")
        else:
            getattr(controller, method)()

    def configure(self):
        if not self._require() or self.busy:
            return
        dialog = ProjectConfigurationDialog(self.store.metadata, self, project_root=self.store.root)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            store = self.store
            self._run(lambda: store.configure(*dialog.configuration), lambda _: self._adopt(store))

    def open_run(self):
        if not self._require():
            return
        runs = self.store.metadata.get("run_configurations", [])
        if not runs:
            self.summary.setText("Add a run configuration in Configure project. Opening a preset never starts Python; select a device and approve Run separately.")
            return
        name, accepted = QInputDialog.getItem(self, "Open script run preset", "Choose saved script (execution still requires approval)", [item.get("name", "") for item in runs], editable=False)
        if accepted:
            store = self.store
            self._run(lambda: store.configured_script(name), lambda path: self.source_selected.emit(str(path), 1))

    def insert_recognition(self):
        if not self._require():
            return
        reference, accepted = QInputDialog.getText(self, "Insert recognition preset", "Existing image target inside this project", text="target.png")
        if accepted:
            store = self.store
            self._run(lambda: store.recognition_code(reference), self.window.insert_code)

    def recover_metadata(self):
        root = QFileDialog.getExistingDirectory(self, "Project with damaged metadata")
        if not root:
            return
        backup, _ = QFileDialog.getOpenFileName(self, "Choose project metadata backup", root, "JSON (*.json);;All files (*)")
        if not backup:
            return
        answer = QMessageBox.question(self, "Recover project metadata", "Restore the selected validated metadata? Current project.json bytes will first be preserved beside it. Scripts, images and task approval are not changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            self._run(lambda: ProjectStore.recover_manifest(root, backup), self._adopt)

    def trash(self):
        if not self._require() or self.busy:
            return
        self.window.shell.documents.remember()
        root = self.store.root
        if any(document.project == root and document.source != document.saved for document in self.window.shell.documents.documents):
            self.summary.setText("Save or close this project's unsaved tabs before moving it to trash.")
            return
        if any(run.exitcode is None for run in self.window.run_states) or self.window.pending_runs:
            self.summary.setText("Stop automation workers and pending starts before moving a project.")
            return
        if self.window.jobs or self.window.recorder.state != "stopped":
            self.summary.setText("Wait for background operations and stop recording before moving a project.")
            return
        if getattr(self.window, "task_store", None) is not None:
            tasks = self.window.task_store.tasks()
            if any(Path(task.project_root) == root and task.enabled for task in tasks):
                self.summary.setText("Disable this project's scheduled tasks before moving it to trash.")
                return
        name = self.store.metadata["name"]
        confirmation, accepted = QInputDialog.getText(self, "Move project to trash", f"This moves every saved file to a sibling .studio-trash folder. Nothing is permanently deleted. Type the exact project name to continue:\n{name}")
        if not accepted:
            return
        store = self.store
        def done(result):
            destination, relocated = result
            tabs = self.window.shell.documents
            for document in tabs.documents:
                if document.project == root:
                    if document.path is not None:
                        document.path = destination / document.path.relative_to(root)
                    document.project = destination
            if self.window.project_root == root:
                if self.window.path is not None:
                    self.window.path = destination / self.window.path.relative_to(root)
                self.window._set_project(destination)
                self.window._update_title()
            self._adopt(relocated)
            self.summary.setText(f"Project preserved in trash: {destination}. Move it back or open that directory to restore it.")
        def relocate():
            destination = store.trash(confirmation)
            return destination, ProjectStore.open(destination)
        self._run(relocate, done)

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
        workflows = task_store.export_workflows(store.root)
        if workflows:
            metadata["workflow_definitions"] = workflows
        return metadata

    def import_tasks(self):
        if not self._require() or self.busy:
            return
        if getattr(self.window, "task_store", None) is None:
            self.summary.setText("Task persistence is unavailable. Project archives remain usable; inspect the Task Manager error.")
            return
        definitions = self.store.metadata.get("task_definitions", [])
        workflows = self.store.metadata.get("workflow_definitions", [])
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
            imported, imported_workflows = self.window.task_store.import_project_definitions(definitions, workflows, self.store.root)
            self.window.task_panel.refresh()
            self.summary.setText(f"Imported {len(imported)} disabled task(s) and {len(imported_workflows)} workflow(s). Review them in Task Manager; execution requires new session approval.")
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


class ProjectConfigurationDialog(QDialog):
    """Edit real persisted presets; unknown execution features are not advertised."""
    def __init__(self, metadata, parent=None, *, project_root=None):
        super().__init__(parent)
        self.setWindowTitle("Project recognition and run configurations")
        self.resize(720, 520)
        self.configuration = None
        self.project_root = Path(project_root) if project_root else None
        layout = QVBoxLayout(self)
        layout.addWidget(label('Recognition presets generate editable Pattern Python. Run presets open a saved Python script; execution still needs an available device and native trust approval.'))
        tabs = QTabWidget()
        recognition = metadata.get("recognition", {})
        page = QWidget()
        form = QFormLayout(page)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 1)
        self.threshold.setDecimals(3)
        self.threshold.setSingleStep(.01)
        try:
            self.threshold.setValue(float(recognition.get("threshold", .85)))
        except (ValueError, TypeError):
            self.threshold.setValue(.85)
        self.scales = QLineEdit(", ".join(str(v) for v in recognition.get("scales", [1.0])))
        self.scales.setPlaceholderText("For example: 0.8, 1.0, 1.2")
        self.preprocessing = QComboBox()
        self.preprocessing.addItems(["none", "grayscale", "threshold", "edges"])
        self.preprocessing.setCurrentText(recognition.get("preprocessing", "none"))
        self.use_region = QCheckBox("Limit matching to a screen region")
        region = recognition.get("region")
        self.use_region.setChecked(region is not None)
        self.region = []
        form.addRow("Similarity threshold", self.threshold)
        form.addRow("Image scales", self.scales)
        form.addRow("Image preprocessing", self.preprocessing)
        form.addRow(self.use_region)
        for index, title in enumerate(("Region X", "Region Y", "Region width", "Region height")):
            control = QSpinBox()
            control.setRange(0 if index < 2 else 1, 65535)
            control.setValue(region[index] if isinstance(region, list) and len(region) == 4 else (0 if index < 2 else 100))
            control.setEnabled(self.use_region.isChecked())
            self.use_region.toggled.connect(control.setEnabled)
            self.region.append(control)
            form.addRow(title, control)
        tabs.addTab(page, "Recognition")
        run_page = QWidget()
        run_layout = QVBoxLayout(run_page)
        self.runs = QTableWidget(0, 2)
        self.runs.setHorizontalHeaderLabels(["Preset name", "Python script in project"])
        self.runs.setAccessibleName("Project script run configurations")
        for entry in metadata.get("run_configurations", []):
            self._add_run(entry.get("name", ""), entry.get("script", ""))
        run_layout.addWidget(self.runs)
        actions = QHBoxLayout()
        actions.addWidget(button("Add script preset…", self._choose_script))
        actions.addWidget(button("Remove selected preset", lambda: self.runs.removeRow(self.runs.currentRow())))
        run_layout.addLayout(actions)
        tabs.addTab(run_page, "Run scripts")
        layout.addWidget(tabs)
        layout.addWidget(label("Presets remain project data. Open a run preset to edit its script; normal Run still requires explicit source and device approval."))
        self.problem = label("", "notice")
        layout.addWidget(self.problem)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self._save)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

    def _save(self):
        try:
            recognition = {"threshold": self.threshold.value(),
                           "scales": [float(v.strip()) for v in self.scales.text().split(",")],
                           "preprocessing": self.preprocessing.currentText()}
            if self.use_region.isChecked():
                recognition["region"] = [item.value() for item in self.region]
            runs = [{"name": self.runs.item(row, 0).text() if self.runs.item(row, 0) else "",
                     "script": self.runs.item(row, 1).text() if self.runs.item(row, 1) else ""}
                    for row in range(self.runs.rowCount())]
            self.configuration = validate_configuration(recognition, runs)
        except (ValueError, TypeError, RecursionError) as error:
            self.problem.setText(str(error))
            return
        self.accept()

    def _add_run(self, name, script):
        row = self.runs.rowCount()
        self.runs.insertRow(row)
        self.runs.setItem(row, 0, QTableWidgetItem(name))
        self.runs.setItem(row, 1, QTableWidgetItem(script))
        self.runs.resizeColumnsToContents()

    def _choose_script(self):
        if self.project_root is None:
            self.problem.setText("Choose a managed project first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose project Python script", str(self.project_root / "scripts"), "Python (*.py)")
        if path:
            try:
                relative = Path(path).resolve().relative_to(self.project_root.resolve()).as_posix()
            except (ValueError, OSError):
                self.problem.setText("The Python script must be inside this project.")
                return
            self._add_run(Path(path).stem, relative)
