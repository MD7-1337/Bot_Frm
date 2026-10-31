"""Beginner connection guidance driven by current, host-owned observations.

The wizard performs no ADB operations itself. The host routes explicit button
requests through its existing asynchronous, serial-specific services. A report
from a previous connection must be passed with report_current=False.
"""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                              QPlainTextEdit, QScrollArea, QSizePolicy, QVBoxLayout,
                              QWidget, QWizard, QWizardPage)

from app.simulation.model import is_simulation
from app.ui.components import button, label


class ObservedPage(QWizardPage):
    def __init__(self, title, subtitle, parent=None):
        super().__init__(parent)
        self.setTitle(title)
        self.setSubTitle(subtitle)
        self.complete = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        body = QWidget()
        self.content = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def isComplete(self):
        return self.complete

    def set_complete(self, value):
        value = bool(value)
        if self.complete != value:
            self.complete = value
            self.completeChanged.emit()


class ConnectionWizard(QWizard):
    refresh_requested = Signal()
    device_selected = Signal(str)
    diagnose_requested = Signal()
    preview_requested = Signal()
    settings_requested = Signal()
    wifi_requested = Signal()
    harmless_test_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect an Android phone")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.resize(760, 620)
        self._selected = None
        self._authorized = False
        self._verified = False
        self._preview_ready = False
        self._busy = False
        self._device_signature = None

        setup = ObservedPage("1. Prepare the phone and computer", "Use a phone and computer you are authorized to control.")
        setup.content.addWidget(label("Connect the unlocked phone using a USB data cable. A charging-only cable cannot carry debugging traffic."))
        setup.content.addWidget(label("On Android, open Settings → About phone and tap Build number seven times if Developer options are not already enabled. Then open Developer options → USB debugging. Menu names vary by manufacturer."))
        setup.content.addWidget(label("Keep the phone unlocked and accept its 'Allow USB debugging?' prompt for this computer. Only trust a computer you control."))
        setup.content.addWidget(label("Windows: the phone manufacturer may require an OEM USB driver. Ubuntu: missing udev/group access needs an authorized administrator. This wizard never changes system permissions or bypasses school policy.", "notice"))
        row = QHBoxLayout()
        row.addWidget(button("Choose ADB / check settings", self.settings_requested.emit))
        row.addWidget(button("Use Wireless debugging instead", self.wifi_requested.emit))
        setup.content.addLayout(row)
        setup.content.addWidget(label("Android 11+ Wireless debugging uses a pairing port/code followed by a separate connection port. The computer and phone must be on a permitted network. Pairing alone is not a verified usable connection."))
        self.prepared = QCheckBox("I have reviewed these steps and am ready to check discovery")
        self.prepared.toggled.connect(setup.set_complete)
        setup.content.addWidget(self.prepared)
        setup.content.addStretch()
        self.addPage(setup)

        self.discovery_page = ObservedPage("2. Find and authorize the phone", "Discovery reports what this computer can currently see.")
        self.device_choice = QComboBox()
        self.device_choice.setAccessibleName("Wizard Android device identity")
        self.device_choice.currentIndexChanged.connect(self._choose_device)
        self.discovery_page.content.addWidget(self.device_choice)
        self.discovery_status = label("No physical Android device has been observed. Demo Mode is separate and cannot satisfy this connection check.", "notice")
        self.discovery_page.content.addWidget(self.discovery_status)
        self.discovery_page.content.addWidget(button("Refresh discovery", self.refresh_requested.emit, primary=True))
        self.discovery_page.content.addWidget(label("Unauthorized: accept the prompt on the phone. Offline: check the cable or Wi-Fi and debugging settings. No permissions: ask the host administrator. Empty discovery can be a cable, driver, USB policy or permission problem; it does not prove an application bug."))
        self.discovery_page.content.addStretch()
        self.addPage(self.discovery_page)

        self.verify_page = ObservedPage("3. Verify this exact phone", "Checks run asynchronously and never send a tap or kill-server command.")
        self.verify_status = label("Run diagnostics. An authorized ADB listing alone is not a usable-device verification.", "notice")
        self.verify_page.content.addWidget(self.verify_status)
        self.diagnose_button = button("Run connection diagnostics", self.diagnose_requested.emit, primary=True)
        self.verify_page.content.addWidget(self.diagnose_button)
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setAccessibleName("Wizard redacted diagnostic observations")
        self.report_view.setPlaceholderText("ADB version, authorization, harmless Android query, screenshot decoding and optional real video results appear here.")
        self.verify_page.content.addWidget(self.report_view, 1)
        self.verify_page.content.addWidget(label("Export or copy the redacted report in Device Manager → Diagnostics. Missing phone-dependent stages stay NOT VERIFIED."))
        self.addPage(self.verify_page)

        self.preview_page = ObservedPage("4. Open a live preview", "Finish requires a current, decoded real-device frame.")
        self.preview_status = label("Live video has not been verified for this connection.", "notice")
        self.preview_page.content.addWidget(self.preview_status)
        self.preview_button = button("Open live preview", self.preview_requested.emit, primary=True)
        self.preview_page.content.addWidget(self.preview_button)
        self.preview_page.content.addWidget(label("The preview opens in the workbench behind this modeless wizard. Check that the phone's live screen matches it. Black protected content may be restricted by Android or the application."))
        self.home_button = button("Optional: test Home on this phone", self._test_home)
        self.home_button.setToolTip("Explicitly send Home to the selected verified phone. This changes its screen; inspect the phone to confirm the result.")
        self.preview_page.content.addWidget(self.home_button)
        self.preview_page.content.addWidget(label("Use a consented test application before testing a tap or swipe. After finishing, Visual Tools can capture a target and test recognition without sending input. Running scripts always requires separate trust approval."))
        self.preview_page.content.addStretch()
        self.addPage(self.preview_page)
        self.update_state([])

    def _choose_device(self, index):
        serial = self.device_choice.itemData(index)
        if serial and serial != self._selected:
            self.device_selected.emit(serial)

    def _test_home(self):
        if self._verified and self._preview_ready and not self._busy and self._selected:
            self.harmless_test_requested.emit(self._selected)
            self.preview_status.setText("Home test requested for this exact phone. Inspect the physical phone's response; this request is not an acknowledgment of input success.")

    def update_state(self, devices, selected_serial=None, *, report=None,
                     report_current=False, preview_ready=False, busy=False):
        """Accept current observations from the host, never infer a reconnect.

        ``report_current`` must be false after selection/generation changes.
        ``preview_ready`` means a fresh decoded scrcpy frame for this exact real
        identity, not an ADB screenshot or simulator frame.
        """
        physical = [device for device in devices if not is_simulation(device.serial)]
        signature = (selected_serial, tuple((device.serial, device.model, device.state) for device in physical))
        if signature != self._device_signature:
            blocker = QSignalBlocker(self.device_choice)
            self.device_choice.clear()
            self.device_choice.addItem("Choose a detected phone", None)
            for device in physical:
                self.device_choice.addItem(f"{device.model or device.serial} · {device.serial} · {device.state}", device.serial)
            self.device_choice.setCurrentIndex(max(0, self.device_choice.findData(selected_serial)))
            del blocker
            self._device_signature = signature
        selected = next((device for device in physical if device.serial == selected_serial), None)
        self._selected = selected.serial if selected else None
        self._authorized = bool(selected and selected.available)
        self._busy = bool(busy)
        self.discovery_page.set_complete(self._authorized)
        self.discovery_status.setText(
            f"Selected {selected.serial}: {selected.state}. This listing is not yet a verified Android query." if selected
            else "No selected physical Android device. Refresh, inspect authorization/driver/permission guidance, then choose the exact identity. Simulated devices are not listed.")
        query_passed = bool(report and any(step.key == "query" and step.state == "passed" for step in report.steps))
        self._verified = bool(self._authorized and report_current and query_passed
                              and getattr(report, "verified_serial", None) == self._selected)
        self.verify_page.set_complete(self._verified)
        self.verify_status.setText("Current authorization and harmless Android query passed for this exact phone." if self._verified
                                   else "NOT VERIFIED: run diagnostics for the selected current connection. An old report cannot authorize a new connection.")
        rendered = report.text() if report is not None else ""
        if self.report_view.toPlainText() != rendered:
            self.report_view.setPlainText(rendered)
        self.diagnose_button.setEnabled(self._authorized and not self._busy)
        self._preview_ready = bool(self._verified and preview_ready)
        self.preview_page.set_complete(self._preview_ready)
        self.preview_status.setText("A current real decoded frame is available. Check the physical phone and preview before testing input." if self._preview_ready
                                    else "NOT VERIFIED: open live preview and wait for a fresh decoded frame. Screenshots and Demo Mode do not satisfy this check.")
        self.preview_button.setEnabled(self._verified and not self._busy)
        self.home_button.setEnabled(self._preview_ready and not self._busy)
