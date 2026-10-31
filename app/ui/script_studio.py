"""Host-owned script tabs and a bounded project explorer; one Monaco instance."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QHBoxLayout, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.ui.components import button, label


@dataclass
class Document:
    path: Path | None
    source: str
    saved: str
    project: Path
    key: str = field(default_factory=lambda: uuid4().hex)


class ScriptTabs(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.documents = [Document(None, "", "", window.project_root)]
        window.editor.set_document_key(self.documents[0].key)
        self.current = 0
        self.switching = False
        if hasattr(window.editor, "background_document_changed"):
            window.editor.background_document_changed.connect(self._background_change)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.bar = QTabBar()
        self.bar.setDocumentMode(True)
        self.bar.setExpanding(False)
        self.bar.setTabsClosable(True)
        self.bar.setAccessibleName("Python script documents")
        self.bar.addTab("Untitled.py")
        self.bar.currentChanged.connect(self.activate)
        self.bar.tabCloseRequested.connect(self.close_document)
        layout.addWidget(self.bar)
        layout.addWidget(window.editor, stretch=1)

    def _background_change(self, key, source):
        # A final keystroke can reach WebChannel after native tab selection.
        # Preserve it on its originating tab instead of losing or misrouting it.
        for index, document in enumerate(self.documents):
            if document.key == key and index != self.current:
                document.source = source
                self.bar.setTabText(index, (document.path.name if document.path else "Untitled.py")
                                    + (" •" if source != document.saved else ""))
                return

    def remember(self):
        if self.switching or not 0 <= self.current < len(self.documents):
            return
        w = self.window
        self.documents[self.current] = Document(w.path, w.editor.source, w.saved_source, w.project_root,
                                                self.documents[self.current].key)
        self.bar.setTabText(self.current, (w.path.name if w.path else "Untitled.py") + (" •" if w.editor.source != w.saved_source else ""))
        self.bar.setTabToolTip(self.current, str(w.path or "Unsaved Python buffer"))

    def activate(self, index):
        if self.switching or not 0 <= index < len(self.documents) or index == self.current:
            return
        self.remember()
        document = self.documents[index]
        old = self.current
        try:
            # Validate the next context before replacing the visible document.
            script_dir = document.path.parent if document.path and document.path.is_relative_to(document.project) else None
            self.window.editor.set_project_root(document.project, script_dir)
        except (ValueError, OSError) as error:
            with QSignalBlocker(self.bar):
                self.bar.setCurrentIndex(old)
            self.window.log(f"Cannot open document context: {error}")
            return
        self.current = index
        self.window.path, self.window.saved_source = document.path, document.saved
        self.window.editor.set_document_key(document.key)
        if hasattr(self.window.editor, "set_document_path"):
            self.window.editor.set_document_path(document.path, document.project)
        self.window.editor.set_text(document.source)
        self.window._set_project(document.project)
        self.window._update_title()

    def add(self, path, source, project):
        self.remember()
        if path is not None:
            for index, document in enumerate(self.documents):
                if document.path and document.path.resolve() == path.resolve():
                    self.bar.setCurrentIndex(index)
                    return
        current = self.documents[self.current]
        if len(self.documents) == 1 and current.path is None and current.source == current.saved:
            self.documents[0] = Document(path, source, source, project)
            self.window.path, self.window.saved_source = path, source
            self.window.editor.set_document_key(self.documents[0].key)
            if hasattr(self.window.editor, "set_document_path"):
                self.window.editor.set_document_path(path, project)
            self.window.editor.set_text(source)
            self.window._set_project(project)
            self.window._update_title()
            return
        if len(self.documents) >= 20:
            raise ValueError("Close a script tab before opening more than 20 documents")
        self.documents.append(Document(path, source, source, project))
        self.bar.addTab(path.name if path else "Untitled.py")
        self.bar.setCurrentIndex(len(self.documents) - 1)

    def close_document(self, index):
        self.bar.setCurrentIndex(index)
        if self.current != index or not self.window._confirm_discard():
            return
        if len(self.documents) == 1:
            self.documents[0] = Document(None, "", "", self.window.project_root)
            self.window.path = None
            self.window.editor.set_document_key(self.documents[0].key)
            if hasattr(self.window.editor, "set_document_path"):
                self.window.editor.set_document_path(None, self.window.project_root)
            self.window.editor.set_text("")
            self.window.saved_source = ""
            self.window._update_title()
            return
        del self.documents[index]
        self.switching = True
        self.bar.removeTab(index)
        self.switching = False
        self.current = -1
        self.activate(min(index, len(self.documents) - 1))


def project_files(root):
    """Bounded, non-symlink traversal. Only Python and images enter the explorer."""
    excluded = {".git", ".venv", ".tools", "__pycache__", ".pytest_cache", "node_modules", "vendor"}
    output = []
    for index, (directory, folders, files) in enumerate(os.walk(root, followlinks=False)):
        if index >= 1000:
            break
        folders[:] = sorted(folder for folder in folders if folder not in excluded and not (Path(directory) / folder).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() in {".py", ".png", ".jpg", ".jpeg", ".bmp", ".webp"} and not path.is_symlink():
                output.append(path.relative_to(root).as_posix())
                if len(output) >= 1000:
                    return output
    return output


class ProjectExplorer(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.request = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QHBoxLayout()
        heading.addWidget(label("PROJECT", "eyebrow"))
        heading.addWidget(button("Open…", window.choose_project))
        layout.addLayout(heading)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName("Project Python scripts and image assets")
        self.tree.itemDoubleClicked.connect(self._open)
        layout.addWidget(self.tree)
        layout.addWidget(button("Refresh project", self.refresh))

    def refresh(self):
        self.request += 1
        request, root = self.request, self.window.project_root
        def finished(files, error):
            if request != self.request or root != self.window.project_root:
                return
            self.tree.clear()
            if error:
                self.window.log(error)
                return
            folders = {"": self.tree.invisibleRootItem()}
            for reference in files:
                path = Path(reference)
                for parent in reversed(path.parents):
                    if str(parent) == ".":
                        continue
                    key = parent.as_posix()
                    if key not in folders:
                        ancestor = parent.parent.as_posix()
                        ancestor = "" if ancestor == "." else ancestor
                        folders[key] = QTreeWidgetItem(folders[ancestor], [parent.name])
                parent = path.parent.as_posix()
                item = QTreeWidgetItem(folders["" if parent == "." else parent], [path.name])
                item.setData(0, Qt.ItemDataRole.UserRole, reference)
                item.setToolTip(0, reference)
            self.tree.expandToDepth(0)
        self.window._submit(lambda: project_files(root), finished)

    def _open(self, item, column):
        reference = item.data(0, Qt.ItemDataRole.UserRole)
        if reference:
            if Path(reference).suffix.lower() == ".py":
                self.window.open_script_path(self.window.project_root / reference)
            else:
                self.window.show_workspace("visual")
                for index in range(self.window.visual_tools.assets.count()):
                    if self.window.visual_tools.assets.item(index).text() == reference:
                        self.window.visual_tools.assets.setCurrentRow(index)
                        break
