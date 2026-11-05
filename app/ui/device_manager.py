"""Connection center with device cards, staged diagnostics and actionable errors."""
from __future__ import annotations

import json
import time

from PySide6.QtCore import QIODevice, QSaveFile, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QGridLayout,
                              QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar,
                              QFileDialog, QMessageBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from app.devices.adb import DeviceInfo, validate_endpoint
from app.ui.components import button, label, scroll, surface


class DeviceManagerPanel(QWidget):
    refresh_requested = Signal()
    preview_requested = Signal()
    capture_requested = Signal()
    run_requested = Signal()
    connect_requested = Signal(str)
    pair_requested = Signal(str)
    disconnect_requested = Signal()
    reconnect_requested = Signal()
    diagnose_requested = Signal()
    cancel_diagnostics_requested = Signal()
    settings_requested = Signal()
    wizard_requested = Signal()
    bug_report_requested = Signal()
    compare_adb_requested = Signal()

    def __init__(self, devices, settings, parent=None):
        super().__init__(parent)
        self.devices, self.settings = devices, settings
        self._shown_serial = None
        self.report = None
        try:
            labels = json.loads(settings.value("device_labels", "{}"))
            self.labels = {serial: value for serial, value in labels.items()
                           if isinstance(serial, str) and isinstance(value, dict)
                           and all(isinstance(value.get(key, ""), str) for key in ("name", "group"))}
        except (ValueError, TypeError, AttributeError):
            self.labels = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.summary = label("Connect your first Android device. USB detection runs automatically.")
        outer.addWidget(self.summary)
        self.connection_status = label("USB: unlock the phone, enable USB debugging and accept this computer. Wi-Fi uses an explicit connection port.", "notice")
        self.connection_status.setAccessibleName("Connection status and next action")
        status_row = QHBoxLayout()
        status_row.addWidget(self.connection_status, stretch=1)
        status_row.addWidget(button("Diagnose Connection", lambda: self.diagnose_requested.emit()))
        status_row.addWidget(button("Connection wizard…", self.wizard_requested.emit))
        outer.addLayout(status_row)
        split = QSplitter()
        self.split = split
        left, listing = surface()
        title = QHBoxLayout()
        title.addWidget(label("YOUR DEVICES", "eyebrow"))
        title.addWidget(button("Refresh devices", self.refresh_requested.emit))
        listing.addLayout(title)
        listing.addWidget(devices, stretch=1)
        self.empty_state = label("No phones detected\n\nConnect a USB data cable and authorize debugging, or use Wireless debugging.\n\nIf this is a managed school PC, Diagnose Connection will identify host permission failures.", "notice")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        listing.addWidget(self.empty_state, stretch=1)
        devices.hide()
        actions = QGridLayout()
        self.preview_button = button("Open preview", self.preview_requested.emit, primary=True)
        self.capture_button = button("Capture region…", self.capture_requested.emit)
        self.run_button = button("Run editor on selected…", self.run_requested.emit)
        self.reconnect_button = button("Reconnect", self.reconnect_requested.emit)
        for i, widget in enumerate((self.preview_button, self.capture_button, self.run_button, self.reconnect_button)):
            actions.addWidget(widget, i // 2, i % 2)
        listing.addLayout(actions)
        split.addWidget(left)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        connection = QWidget()
        layout = QVBoxLayout(connection)
        layout.addWidget(label("Connect over USB", "sectionTitle"))
        layout.addWidget(label("Use a data-capable cable. USB has no address to enter: enable Developer options → USB debugging, then accept the authorization prompt on the unlocked phone."))
        layout.addWidget(label("School computer? USB access can require udev/group permissions. Without administrator access, ask IT; this app cannot bypass host policy. On Windows, the phone may need its OEM driver.", "notice"))
        layout.addWidget(button("ADB path & settings", self.settings_requested.emit))
        layout.addWidget(label("Wireless debugging", "sectionTitle"))
        layout.addWidget(label("Android 11+: pair with its pairing port and six-digit code, then connect with the separate connection port. Both computers must be allowed on the same network."))
        self.endpoint = QLineEdit()
        self.endpoint.setPlaceholderText("192.168.1.20:37123")
        self.endpoint.setAccessibleName("ADB network endpoint")
        self.endpoint.setMaxLength(255)
        layout.addWidget(self.endpoint)
        buttons = QHBoxLayout()
        self.network_buttons = []
        for text, callback in (("Connect", lambda: self._endpoint_action(self.connect_requested)),
                               ("Pair…", lambda: self._endpoint_action(self.pair_requested)),
                               ("Disconnect selected Wi-Fi", self.disconnect_requested.emit)):
            widget = button(text, callback, primary=text == "Connect")
            buttons.addWidget(widget)
            self.network_buttons.append(widget)
        layout.addLayout(buttons)
        layout.addWidget(label("Recent connection activity", "sectionTitle"))
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.document().setMaximumBlockCount(30)
        self.history.setPlaceholderText("Connection attempts and results appear here. Pairing codes are never stored.")
        self.history.setMinimumHeight(70)
        layout.addWidget(self.history, stretch=1)
        self.tabs.addTab(scroll(connection), "Connect")
        details = QWidget()
        details_layout = QVBoxLayout(details)
        self.details = label("Select a phone to inspect its serial and connection state.", "notice")
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.details)
        fields = QFormLayout()
        self.name, self.group = QLineEdit(), QLineEdit()
        for field in (self.name, self.group):
            field.setMaxLength(80)
        fields.addRow("Display name", self.name)
        fields.addRow("Group", self.group)
        details_layout.addLayout(fields)
        labels = QHBoxLayout()
        labels.addWidget(button("Save name / group", self.save_labels))
        labels.addWidget(button("Select group", self.select_group))
        details_layout.addLayout(labels)
        details_layout.addStretch()
        self.tabs.addTab(scroll(details), "Details")
        diagnostics = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics)
        diagnostics_layout.addWidget(label("Find exactly where connection stops", "sectionTitle"))
        diagnostics_layout.addWidget(label("Checks ADB, the server, discovery, authorization, a harmless query, PNG decoding and a real scrcpy frame. No tap, kill-server command or administrator request is issued. ADB itself may restart an incompatible-version server."))
        checks = QHBoxLayout()
        self.check_video = QCheckBox("Include live video check")
        self.check_video.setChecked(True)
        self.redact_serials = QCheckBox("Redact device serials")
        self.redact_serials.setChecked(True)
        self.redact_serials.toggled.connect(self._render_report)
        checks.addWidget(self.check_video)
        checks.addWidget(self.redact_serials)
        diagnostics_layout.addLayout(checks)
        actions = QGridLayout()
        self.diagnose_button = button("Diagnose Connection", self.diagnose_requested.emit, primary=True)
        self.cancel_diagnostics = button("Cancel check", self.cancel_diagnostics_requested.emit)
        self.cancel_diagnostics.setEnabled(False)
        self.copy_report_button = button("Copy Diagnostic Report", self.copy_report)
        self.copy_report_button.setEnabled(False)
        self.export_report_button = button("Export Diagnostics…", self.export_report)
        self.export_report_button.setEnabled(False)
        for index, widget in enumerate((self.diagnose_button, self.cancel_diagnostics, self.copy_report_button, self.export_report_button)):
            actions.addWidget(widget, index // 2, index % 2)
        diagnostics_layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        diagnostics_layout.addWidget(self.progress)
        self.diagnostic_output = QPlainTextEdit()
        self.diagnostic_output.setReadOnly(True)
        self.diagnostic_output.setAccessibleName("Connection diagnostic stages and report")
        self.diagnostic_output.setPlaceholderText("Run diagnostics on this computer, then copy the redacted report. Checks requiring a phone stay NOT VERIFIED until they run successfully.")
        diagnostics_layout.addWidget(self.diagnostic_output, stretch=1)
        diagnostics_layout.addWidget(button("Export Bug Report…", self.bug_report_requested.emit))
        diagnostics_layout.addWidget(button("Compare with external adb.exe…", self.compare_adb_requested.emit))
        self.tabs.addTab(diagnostics, "Diagnostics")
        split.addWidget(self.tabs)
        split.setChildrenCollapsible(False)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 5)
        outer.addWidget(split, stretch=1)
        self._diagnostic_steps = {}
        self.set_available(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        orientation = Qt.Orientation.Vertical if self.width() < 720 else Qt.Orientation.Horizontal
        if self.split.orientation() != orientation:
            self.split.setOrientation(orientation)
            self.split.setSizes([250, 360] if orientation == Qt.Orientation.Vertical else [320, 450])

    def set_available(self, available, busy=False):
        for widget in (self.preview_button, self.capture_button, self.run_button):
            widget.setEnabled(available and not busy)
            widget.setToolTip("Select an authorized idle phone first" if not available or busy else widget.text())

    def show_diagnostics(self):
        self.tabs.setCurrentIndex(2)

    def diagnostic_busy(self, busy):
        self.diagnose_button.setEnabled(not busy)
        self.cancel_diagnostics.setEnabled(busy)
        self.check_video.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self.report = None
            self._diagnostic_steps.clear()
            self.diagnostic_output.clear()
            self.copy_report_button.setEnabled(False)
            self.export_report_button.setEnabled(False)

    def diagnostic_step(self, step):
        self._diagnostic_steps[step.key] = step
        self.diagnostic_output.setPlainText("\n\n".join(f"[{item.state.upper()}] {item.title}\n{item.detail}" + ("\nNext: " + item.advice if item.advice else "") for item in self._diagnostic_steps.values()))

    def set_report(self, report):
        self.report = report
        self._render_report()
        self.copy_report_button.setEnabled(True)
        self.export_report_button.setEnabled(True)

    def _render_report(self):
        if self.report is not None:
            self.diagnostic_output.setPlainText(self.report.text(self.redact_serials.isChecked()))

    def copy_report(self):
        if self.report is not None:
            QApplication.clipboard().setText(self.report.text(self.redact_serials.isChecked()))
            self.connection_status.setText("Diagnostic report copied. Device serial redaction follows the checkbox in Diagnostics.")

    def add_history(self, message):
        self.history.appendPlainText(time.strftime("%H:%M:%S  ") + str(message))

    def export_report(self):
        """Save the same explicit-redaction report as Copy, without screen pixels."""
        if self.report is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export connection diagnostics", "connection-diagnostics.txt", "Text (*.txt)")
        if not path:
            return
        try:
            output = QSaveFile(path)
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            data = self.report.text(self.redact_serials.isChecked()).encode("utf-8")
            if output.write(data) != len(data):
                output.cancelWriting()
                raise OSError(output.errorString())
            if not output.commit():
                raise OSError(output.errorString())
            self.connection_status.setText("Diagnostic report exported. Review host/path details before sharing; no screenshots or pairing codes are included.")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Diagnostic export failed", str(error))

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
        name = label.get("name") or device.model or ("USB permissions required" if set(device.serial) == {"?"} else device.serial)
        group = f" · group: {label['group']}" if label.get("group") else ""
        return f"{name}{group}\n{device.serial} · {'connected' if device.available else device.state}"

    def update_devices(self, devices):
        connected = sum(device.available for device in devices)
        self.summary.setText(f"{connected} connected / {len(devices)} known phones. Ctrl-click selects multiple; actions keep exact ADB serials.")
        self.devices.setVisible(bool(devices))
        self.empty_state.setVisible(not devices)

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
        if guidance:
            self.connection_status.setText(f"{device.state.upper()}: {guidance}")
        android = getattr(self, "android_versions", {}).get(device.serial, "unavailable")
        try:
            validate_endpoint(device.serial)
            transport = "Wi-Fi / TCP"
        except ValueError:
            transport = "ADB transport (USB or discovered service)"
        geometry = (f"{screen.width} × {screen.height}; rotation {screen.orientation if screen.orientation is not None else 'unavailable'}"
                    if screen and device.available else "unavailable")
        self.details.setText(f"Serial: {device.serial}\nModel: {device.model or 'unavailable'}\nAndroid: {android}\n"
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
