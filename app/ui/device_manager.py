"""Visible device management without owning transports or worker execution."""
from __future__ import annotations

import json

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (QFormLayout, QGridLayout, QGroupBox, QLabel, QLineEdit,
                              QPushButton, QVBoxLayout, QWidget)

from app.devices.adb import DeviceInfo, validate_endpoint


class DeviceManagerPanel(QWidget):
    refresh_requested = Signal()
    preview_requested = Signal()
    capture_requested = Signal()
    run_requested = Signal()
    connect_requested = Signal(str)
    pair_requested = Signal(str)
    disconnect_requested = Signal()

    def __init__(self, devices, settings, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.settings = settings
        self._shown_serial = None
        try:
            labels = json.loads(settings.value("device_labels", "{}"))
            self.labels = {serial: value for serial, value in labels.items()
                           if isinstance(serial, str) and isinstance(value, dict)
                           and all(isinstance(value.get(key, ""), str) for key in ("name", "group"))}
        except (ValueError, TypeError, AttributeError):
            self.labels = {}
        layout = QVBoxLayout(self)
        self.summary = QLabel("No devices discovered. Connect USB and authorize debugging, or connect Wi-Fi below.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        layout.addWidget(devices, stretch=1)
        self.details = QLabel("Select a phone to see its connection state.")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        labels = QFormLayout()
        self.name = QLineEdit()
        self.group = QLineEdit()
        for field in (self.name, self.group):
            field.setMaxLength(80)
        labels.addRow("Display name", self.name)
        labels.addRow("Group", self.group)
        layout.addLayout(labels)
        controls = QGridLayout()
        for index, (label, callback) in enumerate((
            ("Save name / group", self.save_labels), ("Select group", self.select_group),
            ("Refresh devices", self.refresh_requested.emit), ("Open preview", self.preview_requested.emit),
            ("Capture region…", self.capture_requested.emit), ("Run editor on selected…", self.run_requested.emit),
        )):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, target=callback: target())
            controls.addWidget(button, index // 2, index % 2)
        layout.addLayout(controls)
        wifi = QGroupBox("USB / Wi-Fi connection")
        wifi_layout = QVBoxLayout(wifi)
        hint = QLabel("USB: enable Developer options → USB debugging; accept this computer on the phone.\n"
                      "Wi-Fi: use Wireless debugging's connection port. Pairing uses a separate port (Android 11+).")
        hint.setWordWrap(True)
        wifi_layout.addWidget(hint)
        self.endpoint = QLineEdit()
        self.endpoint.setPlaceholderText("192.168.1.20:5555 or [IPv6]:port")
        self.endpoint.setAccessibleName("ADB network endpoint")
        self.endpoint.setMaxLength(255)
        wifi_layout.addWidget(self.endpoint)
        buttons = QGridLayout()
        self.network_buttons = []
        for index, (label, callback) in enumerate((
            ("Connect", lambda: self._endpoint_action(self.connect_requested)),
            ("Pair…", lambda: self._endpoint_action(self.pair_requested)),
            ("Disconnect selected Wi-Fi", self.disconnect_requested.emit),
        )):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, target=callback: target())
            buttons.addWidget(button, index // 2, index % 2)
            self.network_buttons.append(button)
        wifi_layout.addLayout(buttons)
        self.connection_status = QLabel("USB disconnection is physical; Wi-Fi actions always target one endpoint.")
        self.connection_status.setWordWrap(True)
        self.connection_status.setTextFormat(Qt.TextFormat.PlainText)
        wifi_layout.addWidget(self.connection_status)
        layout.addWidget(wifi)

    def _endpoint_action(self, signal):
        try:
            signal.emit(validate_endpoint(self.endpoint.text().strip()))
        except ValueError as error:
            self.connection_status.setText(str(error))

    def set_network_busy(self, busy):
        for button in self.network_buttons:
            button.setEnabled(not busy)

    def caption(self, device):
        label = self.labels.get(device.serial, {})
        name = label.get("name") or device.model or device.serial
        group = f" · group: {label['group']}" if label.get("group") else ""
        return f"{name}{group}\n{device.serial} · {'connected' if device.available else device.state}"

    def update_devices(self, devices):
        connected = sum(device.available for device in devices)
        self.summary.setText(f"{connected} connected / {len(devices)} known phones. Ctrl-click selects multiple; actions keep exact ADB serials.")

    def show_device(self, device: DeviceInfo | None, *, script=None, screen=None):
        labels = self.labels.get(device.serial, {}) if device else {}
        serial = device.serial if device else None
        if serial != self._shown_serial:
            self.name.setText(labels.get("name", ""))
            self.group.setText(labels.get("group", ""))
            self._shown_serial = serial
        if device is None:
            self.details.setText("No phone selected. Refresh after connecting a device.")
            return
        guidance = {"unauthorized": "Unlock the phone and accept the USB debugging authorization dialog.",
                    "offline": "Check the cable/Wi-Fi and debugging settings, then refresh.",
                    "disconnected": "Reconnect and refresh. Preview and scripts require an explicit restart.",
                    "no permissions": "Check Linux udev rules/group permissions or Windows OEM USB drivers.",
                    "unknown": "ADB discovery failed or returned an unknown state; controls are disabled."}.get(device.state, "")
        try:
            validate_endpoint(device.serial)
            transport = "Wi-Fi / TCP"
        except ValueError:
            transport = "ADB transport (USB or discovered service)"
        geometry = (f"{screen.width} × {screen.height}; rotation {screen.orientation if screen.orientation is not None else 'unavailable'}"
                    if screen and device.available else "unavailable")
        self.details.setText(f"Serial: {device.serial}\nModel: {device.model or 'unavailable'}\n"
                             f"State: {'connected' if device.available else device.state} · {transport}\n"
                             f"Screen: {geometry}\nAssigned script: {script or 'none'}\n{guidance}")

    def save_labels(self):
        item = self.devices.currentItem()
        if item is None:
            return
        device = item.data(Qt.ItemDataRole.UserRole)
        self.labels[device.serial] = {"name": self.name.text().strip(), "group": self.group.text().strip()}
        self.settings.setValue("device_labels", json.dumps(self.labels, ensure_ascii=False))
        self.settings.sync()
        item.setText(self.caption(device))

    def select_group(self):
        item = self.devices.currentItem()
        if item is None:
            return
        serial = item.data(Qt.ItemDataRole.UserRole).serial
        group = self.labels.get(serial, {}).get("group")
        if not group:
            self.connection_status.setText("Save a group on the selected phone first.")
            return
        blocker = QSignalBlocker(self.devices)
        for row in range(self.devices.count()):
            candidate = self.devices.item(row)
            identity = candidate.data(Qt.ItemDataRole.UserRole).serial
            candidate.setSelected(self.labels.get(identity, {}).get("group") == group)
        del blocker
