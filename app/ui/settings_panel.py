"""Stitch Settings layout over the application's existing persisted options."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
                              QHBoxLayout, QLabel, QLineEdit, QListWidget, QSpinBox,
                              QStackedWidget, QVBoxLayout, QWidget)

from app.devices.paths import adb_executable
from app.settings import integer, theme_name
from app.ui.components import button, scroll


def number(low, high, value):
    widget = QSpinBox()
    widget.setRange(low, high)
    widget.setValue(value)
    return widget


class SettingsPanel(QWidget):
    apply_requested = Signal(object)
    save_requested = Signal(object)
    check_ocr_requested = Signal()
    check_health_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(210)
        self.navigation.addItems(["Android Connection", "Phone Preview", "Script Editor",
                                  "Automation", "Recognition", "Privacy & Diagnostics"])
        body.addWidget(self.navigation)
        self.sections = QStackedWidget()
        body.addWidget(self.sections, stretch=1)
        outer.addLayout(body, stretch=1)

        connection, form = self._section("Android Connection", "Configure ADB executable routing and device discovery.")
        self.adb_path = QLineEdit(settings.value("adb_path", ""))
        self.adb_path.setPlaceholderText("Automatic ADB executable")
        form.addRow("Executable Path (adb.exe)", self._browse_row(self.adb_path, self.choose_adb))
        self.effective_path = QLabel("Currently selected: " + adb_executable(settings.value("adb_path", "")))
        self.effective_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Status", self.effective_path)
        self.discovery = number(1, 15, integer(settings, "discovery_seconds", 3, 1, 15))
        self.discovery.setSuffix(" seconds")
        form.addRow("USB Hotplug Poll Rate", self.discovery)
        connection.addWidget(button("Check Availability", self.check_health_requested.emit))
        connection.addStretch()

        preview, form = self._section("Phone Preview", "Configure scrcpy streaming and screenshot capture quality.")
        self.server_path = QLineEdit(settings.value("scrcpy_server_path", ""))
        self.server_path.setPlaceholderText("Automatic pinned scrcpy 3.1 server")
        form.addRow("scrcpy 3.1 Server Path", self.server_path)
        self.fps = number(1, 60, integer(settings, "stream_fps", 30, 1, 60))
        self.fps.setSuffix(" FPS")
        self.bitrate = number(1, 32, integer(settings, "stream_bitrate", 8, 1, 32))
        self.bitrate.setSuffix(" Mbps")
        self.max_size = number(256, 4096, integer(settings, "stream_size", 1280, 256, 4096))
        self.max_size.setSuffix(" px")
        for name, widget in (("Maximum FPS Limit", self.fps), ("Video Bitrate Limit", self.bitrate),
                             ("Maximum Preview Resolution", self.max_size)):
            form.addRow(name, widget)
        preview.addStretch()

        editor, form = self._section("Script Editor", "Manage syntax styling and editor typography.")
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(theme_name(settings))
        self.font_size = number(10, 24, integer(settings, "editor_font_size", 14, 10, 24))
        self.font_size.setSuffix(" px")
        form.addRow("Editor Theme", self.theme)
        form.addRow("Font Size", self.font_size)
        editor.addStretch()

        automation, form = self._section("Automation", "Configure existing script worker concurrency.")
        self.workers = number(1, 8, integer(settings, "worker_limit", 4, 1, 8))
        self.workers.setSuffix(" threads")
        form.addRow("Worker Thread Limit", self.workers)
        automation.addStretch()

        recognition, form = self._section("Recognition", "Configure optional offline Tesseract OCR.")
        self.ocr_path = QLineEdit(settings.value("ocr_executable", ""))
        self.ocr_path.setPlaceholderText("Automatic: STUDIO_TESSERACT or tesseract on PATH")
        form.addRow("Tesseract OCR Executable Route", self._browse_row(self.ocr_path, self.choose_ocr))
        recognition.addWidget(button("Check Availability", self.check_ocr_requested.emit))
        self.ocr_status = QLabel("OCR has not been checked on this computer.")
        recognition.addWidget(self.ocr_status)
        recognition.addStretch()

        privacy, form = self._section("Privacy & Diagnostics", "Control sensitive details in local diagnostic reports.")
        self.redact = QCheckBox("Redact device serials in copied diagnostic reports")
        self.redact.setChecked(settings.value("redact_diagnostics", True, type=bool))
        form.addRow(self.redact)
        self.log_path = QLabel("Application event log: unavailable")
        self.log_path.setWordWrap(True)
        self.log_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        privacy.addWidget(self.log_path)
        privacy.addStretch()

        self.navigation.currentRowChanged.connect(self.sections.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        footer = QHBoxLayout()
        footer.setContentsMargins(12, 8, 12, 8)
        self.result = QLabel("Settings stored for this user")
        self.result.setObjectName("stitchMetadata")
        footer.addWidget(self.result, stretch=1)
        footer.addWidget(button("Cancel", self._cancel))
        footer.addWidget(button("Apply", self.apply))
        footer.addWidget(button("Save & Apply", self.save, primary=True))
        outer.addLayout(footer)

    def _section(self, title, description):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 14, 18, 14)
        heading = QLabel(title)
        heading.setObjectName("stitchHeading")
        layout.addWidget(heading)
        subtitle = QLabel(description)
        subtitle.setObjectName("stitchMetadata")
        layout.addWidget(subtitle)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        form = QFormLayout()
        form.setSpacing(12)
        layout.addLayout(form)
        self.sections.addWidget(scroll(content))
        return layout, form

    @staticmethod
    def _browse_row(field, callback):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field, stretch=1)
        row.addWidget(button("Browse…", callback))
        return holder

    def _cancel(self):
        dialog = self.window()
        if hasattr(dialog, "reject"):
            dialog.reject()

    def choose_adb(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose ADB executable", self.adb_path.text() or str(Path.home()), "ADB executable (adb adb.exe);;All files (*)")
        if path:
            self.adb_path.setText(path)

    def choose_ocr(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Tesseract executable", self.ocr_path.text() or str(Path.home()), "Tesseract (tesseract tesseract.exe);;All files (*)")
        if path:
            self.ocr_path.setText(path)

    def values(self):
        return {"theme": self.theme.currentText(), "editor_font_size": self.font_size.value(),
                "adb_path": self.adb_path.text().strip(), "scrcpy_server_path": self.server_path.text().strip(),
                "stream_fps": self.fps.value(), "stream_bitrate": self.bitrate.value(),
                "stream_size": self.max_size.value(), "worker_limit": self.workers.value(),
                "discovery_seconds": self.discovery.value(), "redact_diagnostics": self.redact.isChecked(),
                "ocr_executable": self.ocr_path.text().strip()}

    def apply(self):
        self.apply_requested.emit(self.values())

    def save(self):
        self.save_requested.emit(self.values())
