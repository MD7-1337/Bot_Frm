"""Only implemented settings; platform permissions remain outside the application."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                              QLineEdit, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from app.devices.paths import adb_executable
from app.settings import integer, theme_name
from app.ui.components import button, label, scroll


def number(low, high, value):
    widget = QSpinBox()
    widget.setRange(low, high)
    widget.setValue(value)
    return widget


class SettingsPanel(QWidget):
    apply_requested = Signal(object)
    check_ocr_requested = Signal()
    check_health_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        appearance = QWidget()
        layout = QVBoxLayout(appearance)
        layout.addWidget(label("Make the studio yours", "sectionTitle"))
        form = QFormLayout()
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(theme_name(settings))
        self.font_size = number(10, 24, integer(settings, "editor_font_size", 14, 10, 24))
        form.addRow("Color theme", self.theme)
        form.addRow("Editor font size", self.font_size)
        layout.addLayout(form)
        layout.addWidget(label("The sidebar can collapse. Drag workspace splitters to resize the editor, project tree, preview and execution panels. Sizes and the last workspace are saved for this user.", "notice"))
        layout.addStretch()
        tabs.addTab(appearance, "Appearance")
        tools = QWidget()
        layout = QVBoxLayout(tools)
        layout.addWidget(label("Android tools", "sectionTitle"))
        layout.addWidget(label("No administrator access is required to choose a local ADB binary. USB permission and driver policy still belong to the host computer."))
        form = QFormLayout()
        self.adb_path = QLineEdit(settings.value("adb_path", ""))
        self.adb_path.setPlaceholderText("Automatic (STUDIO_ADB, PATH, then local tools)")
        self.adb_path.setClearButtonEnabled(True)
        form.addRow("ADB executable", self.adb_path)
        layout.addLayout(form)
        layout.addWidget(button("Choose ADB executable…", self.choose_adb))
        self.effective_path = label("Currently selected: " + adb_executable(settings.value("adb_path", "")), "notice")
        self.effective_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.effective_path)
        self.server_path = QLineEdit(settings.value("scrcpy_server_path", ""))
        self.server_path.setPlaceholderText("Automatic pinned scrcpy 3.1 server")
        form = QFormLayout()
        form.addRow("scrcpy 3.1 server", self.server_path)
        self.fps = number(1, 60, integer(settings, "stream_fps", 30, 1, 60))
        self.bitrate = number(1, 32, integer(settings, "stream_bitrate", 8, 1, 32))
        self.max_size = number(256, 4096, integer(settings, "stream_size", 1280, 256, 4096))
        form.addRow("Maximum FPS", self.fps)
        form.addRow("Bitrate (Mbit/s)", self.bitrate)
        form.addRow("Maximum edge (px)", self.max_size)
        layout.addLayout(form)
        layout.addWidget(label("Tool changes require all runs, diagnostics, jobs and live previews to be idle. Stream options apply at the next start. STUDIO_ADB and STUDIO_SCRCPY_SERVER override saved tool paths.", "notice"))
        layout.addWidget(button("Check dependency health…", self.check_health_requested.emit))
        layout.addStretch()
        tabs.addTab(scroll(tools), "Devices & video")
        automation = QWidget()
        layout = QVBoxLayout(automation)
        layout.addWidget(label("Execution & discovery", "sectionTitle"))
        form = QFormLayout()
        self.workers = number(1, 8, integer(settings, "worker_limit", 4, 1, 8))
        self.discovery = number(1, 15, integer(settings, "discovery_seconds", 3, 1, 15))
        form.addRow("Worker limit (next launch)", self.workers)
        form.addRow("USB discovery interval (s)", self.discovery)
        layout.addLayout(form)
        layout.addWidget(label("One worker owns one phone. Normal Python has your user permissions; trust approval and emergency stop remain mandatory parts of execution. Changing the worker limit does not interrupt current runs.", "notice"))
        layout.addStretch()
        tabs.addTab(automation, "Automation")
        recognition = QWidget()
        recognition_layout = QVBoxLayout(recognition)
        recognition_layout.addWidget(label("Offline OCR (optional)", "sectionTitle"))
        recognition_layout.addWidget(label("Tesseract 5 and local traineddata provide text recognition. Nothing is downloaded or installed automatically. Choose an existing trusted executable; models can be supplied under TESSDATA_PREFIX."))
        self.ocr_path = QLineEdit(settings.value("ocr_executable", ""))
        self.ocr_path.setPlaceholderText("Automatic: STUDIO_TESSERACT or tesseract on PATH")
        recognition_layout.addWidget(self.ocr_path)
        def choose_ocr():
            path,_ = QFileDialog.getOpenFileName(self,"Choose Tesseract executable",self.ocr_path.text(),"Tesseract (tesseract tesseract.exe);;All files (*)")
            if path:
                self.ocr_path.setText(path)
        recognition_layout.addWidget(button("Choose OCR executable…",choose_ocr))
        recognition_layout.addWidget(button("Check OCR engine and languages",self.check_ocr_requested.emit))
        self.ocr_status = label("OCR has not been checked on this computer.", "notice")
        recognition_layout.addWidget(self.ocr_status)
        recognition_layout.addStretch()
        tabs.addTab(recognition,"Recognition")
        privacy = QWidget()
        layout = QVBoxLayout(privacy)
        layout.addWidget(label("Local by default", "sectionTitle"))
        self.redact = QCheckBox("Redact serials in copied diagnostic reports by default")
        self.redact.setChecked(settings.value("redact_diagnostics", True, type=bool))
        layout.addWidget(self.redact)
        layout.addWidget(label("No telemetry or cloud account is required. Connection diagnostics do not retain screen pixels or pairing codes. Screenshots, scripts and recorder sessions are saved only when you choose a file; review them before sharing.", "notice"))
        layout.addStretch()
        tabs.addTab(privacy, "Privacy")
        outer.addWidget(tabs, stretch=1)
        footer = QHBoxLayout()
        self.result = label("Changes apply to this user. No system settings are modified.")
        footer.addWidget(self.result, stretch=1)
        footer.addWidget(button("Apply settings", self.apply, primary=True))
        outer.addLayout(footer)

    def choose_adb(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Android platform-tools ADB executable", self.adb_path.text() or str(Path.home()), "ADB executable (adb adb.exe);;All files (*)")
        if path:
            self.adb_path.setText(path)

    def apply(self):
        self.apply_requested.emit({"theme": self.theme.currentText(), "editor_font_size": self.font_size.value(),
            "adb_path": self.adb_path.text().strip(), "scrcpy_server_path": self.server_path.text().strip(),
            "stream_fps": self.fps.value(), "stream_bitrate": self.bitrate.value(), "stream_size": self.max_size.value(),
            "worker_limit": self.workers.value(), "discovery_seconds": self.discovery.value(), "redact_diagnostics": self.redact.isChecked(),
            "ocr_executable": self.ocr_path.text().strip()})
