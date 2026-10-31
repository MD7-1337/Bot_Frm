from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel

from app.editor.bridge import EditorBridge
from app.editor.assets import MonacoAssetsError, validate_monaco
from app.resources import resource_root

EDITOR_ROOT = resource_root() / "editor_web"


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        allowed = url.scheme() in ("data", "blob")
        if url.scheme() == "qrc":
            allowed = url.path() == "/qtwebchannel/qwebchannel.js"
        if url.isLocalFile():
            try:
                allowed = Path(url.toLocalFile()).resolve().is_relative_to(EDITOR_ROOT.resolve())
            except (OSError, RuntimeError):
                allowed = False
        info.block(not allowed)


class EditorPage(QWebEnginePage):
    console_error = Signal(str)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return url == QUrl.fromLocalFile(str(EDITOR_ROOT / "index.html"))

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.console_error.emit("Local editor JavaScript error: " + message[:1500])


class EditorWidget(QWidget):
    ready = Signal()
    document_changed = Signal(str)
    error = Signal(str)
    breakpoints_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = ""
        self.is_ready = False
        self._initialization_failed = False
        self._breakpoints = ()
        self._document_key = "default"
        self._document_breakpoints = {}
        self.execution_line = None
        self.run_status = "Idle"
        self.appearance = ("dark", 14)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel("Loading local Monaco editor…")
        layout.addWidget(self.status)
        self.run_status_label = QLabel("Idle")
        self.run_status_label.setAccessibleName("Script execution status")
        layout.addWidget(self.run_status_label)
        self.view = QWebEngineView(self)
        # Off-the-record profile: no cookies or browser data persisted.
        self.profile = QWebEngineProfile(self)
        self.interceptor = LocalRequests(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page = EditorPage(self.profile, self.view)
        self.page.console_error.connect(self._on_error)
        self.view.setPage(self.page)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.channel = QWebChannel(self.page)
        self.bridge = EditorBridge(self.channel)
        self.channel.registerObject("editorBridge", self.bridge)
        self.page.setWebChannel(self.channel)
        self.bridge.ready.connect(self._on_ready)
        self.bridge.changed.connect(self._on_change)
        self.bridge.failed.connect(self._on_error)
        self.bridge.breakpoints_changed.connect(self._on_breakpoints)
        self.view.loadFinished.connect(self._loaded)
        self.view.renderProcessTerminated.connect(lambda *_: self._on_error("Editor renderer stopped. Restart the application; run --health if it repeats."))
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(lambda: self._on_error("Monaco initialization timed out. Run python -m app.main --health, then repair local assets with python tools/fetch_monaco.py."))
        layout.addWidget(self.view, stretch=1)
        try:
            validate_monaco(EDITOR_ROOT)
        except (MonacoAssetsError, OSError, ValueError) as error:
            self._on_error(str(error))
        else:
            self.startup_timer.start(15000)
            self.view.load(QUrl.fromLocalFile(str(EDITOR_ROOT / "index.html")))

    def _loaded(self, ok: bool):
        if not ok:
            self._on_error("Local editor page could not be loaded")

    def _on_ready(self):
        if self._initialization_failed or self.is_ready:
            return
        self.startup_timer.stop()
        self.is_ready = True
        self.status.hide()
        self.set_text(self.source)
        self.set_execution_line(self.execution_line)
        self.set_run_status(self.run_status)
        self.set_appearance(*self.appearance)
        self.set_breakpoints(self._breakpoints)
        self.ready.emit()

    def _on_change(self, source: str):
        self.source = source
        self.document_changed.emit(source)

    def _on_error(self, message: str):
        self.startup_timer.stop()
        self._initialization_failed = True
        self.is_ready = False
        self.status.setText(message)
        self.status.show()
        self.error.emit(message)

    def _on_breakpoints(self, lines):
        if isinstance(lines, dict):
            if lines["key"] != self._document_key:
                return
            lines = lines["lines"]
        self._breakpoints = tuple(lines)
        self.breakpoints_changed.emit(list(lines))

    def get_breakpoints(self) -> tuple[int, ...]:
        return self._breakpoints

    @property
    def breakpoints(self) -> list[int]:
        return list(self._breakpoints)

    def set_document_key(self, key: str):
        """Select host-owned source identity before loading another script buffer."""
        if not isinstance(key, str) or len(key) > 4096:
            raise ValueError("Document identity must be a bounded string")
        if key != self._document_key:
            self._document_breakpoints[self._document_key] = self._breakpoints
            self._document_key = key
            self._breakpoints = self._document_breakpoints.get(key, ())

    def set_breakpoints(self, lines):
        lines = tuple(sorted(set(lines)))
        if len(lines) > 1000 or any(type(line) is not int or not 1 <= line <= 1_000_000 for line in lines):
            raise ValueError("Breakpoints require at most 1000 positive source line numbers")
        self._breakpoints = lines
        if self.is_ready:
            self.page.runJavaScript("window.studio.setBreakpoints(" + json.dumps(lines) + "," + json.dumps(self._document_key) + ")")

    def set_text(self, source: str):
        if len(source) > 1_000_000:
            raise ValueError("Document exceeds editor size limit")
        self.source = source
        if self.is_ready:
            self.page.runJavaScript("window.studio.setText(" + json.dumps(source) + "," + json.dumps(self._document_key) + "," + json.dumps(self._breakpoints) + ")")

    def insert(self, source: str):
        if self.is_ready:
            self.page.runJavaScript("window.studio.insert(" + json.dumps(source) + ")")

    def set_project_root(self, root: Path | str | None, script_dir: Path | str | None = None):
        """Set the host-selected image library; the page cannot change it."""
        self.bridge.set_project_root(root, script_dir)
        if self.is_ready:
            self.page.runJavaScript("window.studio.refreshImages()")

    def set_execution_line(self, line: int | None):
        """Decorate an observed worker line independently of editable source."""
        if line is not None and (type(line) is not int or line < 1):
            raise ValueError("Execution line must be a positive integer or None")
        self.execution_line = line
        if self.is_ready:
            self.page.runJavaScript("window.studio.setExecutionLine(" + json.dumps(line) + ")")

    def set_run_status(self, text: str):
        if not isinstance(text, str):
            raise ValueError("Run status must be text")
        self.run_status = text[:500]
        self.run_status_label.setText(self.run_status)
        if self.is_ready:
            self.page.runJavaScript("window.studio.setRunStatus(" + json.dumps(self.run_status) + ")")

    def reveal_line(self, line: int):
        """Navigate to a host-validated failure line without changing source."""
        if type(line) is not int or line < 1:
            raise ValueError("Source line must be a positive integer")
        if self.is_ready:
            self.page.runJavaScript(f"window.studio.editor.setPosition({{lineNumber:{line},column:1}});window.studio.editor.revealLineInCenter({line});window.studio.editor.focus();")

    def shutdown(self):
        self.startup_timer.stop()
        self.page.setWebChannel(None)
        self.view.setPage(None)
        self.page.deleteLater()

    def set_appearance(self, theme: str, font_size: int):
        if theme not in ("light", "dark") or type(font_size) is not int or not 10 <= font_size <= 24:
            raise ValueError("Editor appearance requires light/dark and a font size from 10 to 24")
        self.appearance = theme, font_size
        if self.is_ready:
            self.page.runJavaScript("window.studio.setAppearance(" + json.dumps(theme) + "," + str(font_size) + ")")
