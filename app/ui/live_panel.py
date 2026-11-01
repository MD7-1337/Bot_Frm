"""Multi-device preview presentation; transport stays outside Qt widgets."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                              QLabel, QMenu, QPushButton, QScrollArea, QSpinBox, QToolButton,
                              QSizePolicy, QVBoxLayout, QWidget)

from app.ui.components import button, label

from app.streaming.manager import StreamOptions
from app.ui.preview import PhonePreview


class LivePanel(QWidget):
    start_requested = Signal()
    start_all_requested = Signal()
    stop_requested = Signal()
    fallback_requested = Signal()
    home_requested = Signal()
    back_requested = Signal()
    capture_requested = Signal()

    def __init__(self, selected: PhonePreview, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(label("PHONE PREVIEW", "eyebrow"), stretch=1)
        self.configure = button("Quality", self._toggle_quality)
        heading.addWidget(self.configure)
        layout.addLayout(heading)
        self.status = label("Connect and select a phone, then start live video.", "notice")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.status)
        self.quality = QGroupBox("Next stream settings")
        settings = QFormLayout(self.quality)
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
        for text, widget in (("FPS", self.fps), ("Bitrate", self.bitrate), ("Maximum edge", self.max_size)):
            widget.setToolTip("Applied at stream start. Stop the stream before changing settings.")
            settings.addRow(text, widget)
        self.quality.hide()
        layout.addWidget(self.quality)
        controls = QHBoxLayout()
        self.start_button = button("Start live", self.start_requested.emit, primary=True)
        self.stop_button = button("Stop", self.stop_requested.emit)
        self.more = QToolButton()
        self.more.setText("More")
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more)
        self.start_all_action = menu.addAction("Start all connected")
        self.start_all_action.triggered.connect(lambda: self.start_all_requested.emit())
        self.fallback_action = menu.addAction("Screenshot fallback")
        self.fallback_action.triggered.connect(lambda: self.fallback_requested.emit())
        self.more.setMenu(menu)
        for widget in (self.start_button, self.stop_button, self.more):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.geometry_label = label("Original resolution: awaiting a frame")
        self.geometry_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.geometry_label)
        # Native Windows font metrics can make three buttons wider than the
        # narrow preview slot. Keep every input/capture control reachable.
        android = QGridLayout()
        self.back_button = button("Back", self.back_requested.emit)
        self.home_button = button("Home", self.home_requested.emit)
        self.capture_button = button("Capture", self.capture_requested.emit)
        android.addWidget(self.back_button, 0, 0)
        android.addWidget(self.home_button, 0, 1)
        android.addWidget(self.capture_button, 1, 0, 1, 2)
        layout.addLayout(android)
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

    def _toggle_quality(self):
        self.quality.setVisible(not self.quality.isVisible())

    def set_control_state(self, available, can_input, state="stopped"):
        self.start_button.setEnabled(available and state not in ("starting", "streaming", "stopping"))
        self.stop_button.setEnabled(state in ("starting", "streaming"))
        self.fallback_action.setEnabled(available)
        self.start_all_action.setEnabled(available)
        for widget in (self.back_button, self.home_button):
            widget.setEnabled(can_input)
            widget.setToolTip("Send to the selected phone" if can_input else "Select an idle authorized phone and reset emergency stop")
        self.capture_button.setEnabled(available)

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
