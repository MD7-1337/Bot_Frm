"""Multi-device preview presentation; transport stays outside Qt widgets."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                              QLabel, QPushButton, QScrollArea, QSpinBox,
                              QVBoxLayout, QWidget)

from app.streaming.manager import StreamOptions
from app.ui.preview import PhonePreview


class LivePanel(QWidget):
    start_requested = Signal()
    start_all_requested = Signal()
    stop_requested = Signal()
    fallback_requested = Signal()

    def __init__(self, selected: PhonePreview, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.status = QLabel("Select an authorized phone. Live video starts only on request.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        settings = QFormLayout()
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(30)
        self.fps.setSuffix(" FPS")
        self.bitrate = QSpinBox()
        self.bitrate.setRange(1, 32)
        self.bitrate.setValue(8)
        self.bitrate.setSuffix(" Mbit/s")
        self.max_size = QSpinBox()
        self.max_size.setRange(256, 4096)
        self.max_size.setSingleStep(128)
        self.max_size.setValue(1280)
        self.max_size.setSuffix(" px")
        for label, widget in (("Maximum FPS", self.fps), ("Video bitrate", self.bitrate), ("Maximum edge", self.max_size)):
            widget.setToolTip("Applied when starting a stream. Stop first to change an active session.")
            settings.addRow(label, widget)
        layout.addLayout(settings)
        buttons = QGridLayout()
        for index, (text, signal) in enumerate((("Start live", self.start_requested),
                                               ("Stop live", self.stop_requested),
                                               ("Start all connected", self.start_all_requested),
                                               ("Screenshot fallback", self.fallback_requested))):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, target=signal: target.emit())
            buttons.addWidget(button, index // 2, index % 2)
        layout.addLayout(buttons)
        self.geometry_label = QLabel("Resolution / orientation: unavailable")
        layout.addWidget(self.geometry_label)
        content = QWidget()
        contents = QVBoxLayout(content)
        contents.setContentsMargins(0, 0, 0, 0)
        contents.addWidget(selected)
        self.tiles_layout = QVBoxLayout()
        contents.addLayout(self.tiles_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.tiles: dict[str, tuple[QGroupBox, PhonePreview, QLabel]] = {}

    def options(self):
        return StreamOptions(max_fps=self.fps.value(), bitrate=self.bitrate.value() * 1_000_000,
                             max_size=self.max_size.value())

    def tile(self, serial: str) -> PhonePreview:
        if serial not in self.tiles:
            box = QGroupBox(serial)
            layout = QVBoxLayout(box)
            status = QLabel("Waiting for live frames")
            status.setWordWrap(True)
            preview = PhonePreview()
            layout.addWidget(status)
            layout.addWidget(preview)
            self.tiles_layout.addWidget(box)
            self.tiles[serial] = (box, preview, status)
        return self.tiles[serial][1]

    def update_status(self, serial, state, selected_serial):
        if serial in self.tiles:
            box, _, label = self.tiles[serial]
            box.setVisible(serial != selected_serial)
            label.setText(state)
        if serial == selected_serial:
            self.status.setText(f"{serial} · {state}")
