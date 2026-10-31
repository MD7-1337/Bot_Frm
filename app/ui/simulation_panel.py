"""Opt-in demo controls, separate from ADB connection controls."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from app.simulation.model import LABEL, SCENARIOS
from app.ui.components import button, label


class SimulationPanel(QScrollArea):
    start_requested = Signal()
    reset_requested = Signal()
    stop_requested = Signal()
    example_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        content = QWidget()
        self.setWidgetResizable(True)
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.addWidget(label(LABEL, "notice"))
        layout.addWidget(label("Build and test without a phone", "sectionTitle"))
        layout.addWidget(label("The demo uses the same editor, OpenCV, screenshot tools, recorder and isolated Python workers. Actions change locally simulated screens; no ADB commands are sent to a demo identity."))
        form = QFormLayout()
        self.scenario = QComboBox()
        for key, name in SCENARIOS.items():
            self.scenario.addItem(name, key)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 60)
        self.delay.setValue(2)
        self.delay.setSuffix(" s")
        form.addRow("Scenario", self.scenario)
        form.addRow("Appearance delay", self.delay)
        layout.addLayout(form)
        layout.addWidget(button("Start Demo Session", self.start_requested.emit, primary=True))
        row = QHBoxLayout()
        self.reset_button = button("Reset Demo", self.reset_requested.emit)
        self.stop_button = button("Stop Demo", self.stop_requested.emit)
        row.addWidget(self.reset_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.example_button = button("Open scenario script", self.example_requested.emit)
        layout.addWidget(self.example_button)
        self.status = label("No demo active. Start explicitly; a failed real connection never selects simulation.", "notice")
        layout.addWidget(self.status)
        layout.addWidget(label("Each session creates a fresh demo project with real image targets and example scripts. Use the header selector to choose between independent demos and real phones. Reset cancels old work; Stop disconnects only that simulator."))
        layout.addStretch()
        self.set_active(False)

    def options(self):
        return self.scenario.currentData(), self.delay.value()

    def set_active(self, active):
        self.reset_button.setEnabled(active)
        self.stop_button.setEnabled(active)
        self.example_button.setEnabled(active)
