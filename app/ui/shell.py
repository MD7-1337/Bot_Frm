"""Workspace-based IDE shell; existing services and widgets retain their owners."""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QSplitter, QStackedWidget,
                              QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from app.ui.components import button, label, surface
from app.ui.design import icon
from app.ui.script_studio import ProjectExplorer, ScriptTabs
from app.ui.settings_panel import SettingsPanel
from app.simulation.model import LABEL as SIMULATION_LABEL, is_simulation

WORKSPACES = {
    "studio": ("Script Studio", "Write Python. Build visual actions. Run on the phone you choose."),
    "devices": ("Device Manager", "Connect, authorize and diagnose your Android devices."),
    "visual": ("Visual Tools", "Capture targets and test recognition against a fresh screen."),
    "recorder": ("Recorder", "Turn studio controls into an editable Python workflow."),
    "monitor": ("Activity & Logs", "Independent runs, errors and output in one place."),
    "tasks": ("Task Manager", "Scheduling is planned; current execution uses explicit script assignments."),
    "settings": ("Settings", "A local setup that works for your computer and your devices."),
}


class WorkspaceShell(QWidget):
    def __init__(self, window):
        super().__init__()
        self.setObjectName("workspaceShell")
        self.window = window
        self.current = "studio"
        self.user_collapsed = window.settings.value("sidebar_collapsed", False, type=bool)
        self.preview_on_small = False
        self._selector_signature = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 6)
        layout.setSpacing(12)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(190)
        sidebar = QVBoxLayout(self.sidebar)
        sidebar.setContentsMargins(10, 14, 10, 12)
        sidebar.setSpacing(6)
        self.brand = label("ANDROID\nAUTOMATION", "brand")
        sidebar.addWidget(self.brand)
        self.alpha = label("STUDIO  /  ALPHA", "eyebrow")
        sidebar.addWidget(self.alpha)
        self.nav = {}
        for key, (title, _) in WORKSPACES.items():
            item = QToolButton()
            item.setObjectName("navButton")
            item.setText(title)
            item.setAccessibleName(title + " workspace")
            item.setToolTip(title)
            item.setIcon(icon(key))
            item.setIconSize(QSize(21, 21))
            item.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            item.setCheckable(True)
            item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            item.clicked.connect(lambda checked=False, name=key: window.show_workspace(name))
            sidebar.addWidget(item)
            self.nav[key] = item
        sidebar.addStretch()
        self.collapse = button("Collapse sidebar", self.toggle_sidebar)
        sidebar.addWidget(self.collapse)
        self.local_label = label("LOCAL WORKSPACE", "eyebrow")
        sidebar.addWidget(self.local_label)
        layout.addWidget(self.sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(10)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.title = label("Script Studio", "workspaceTitle")
        self.subtitle = label(WORKSPACES["studio"][1])
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, stretch=1)
        self.device_selector = QComboBox()
        self.device_selector.setAccessibleName("Active Android device")
        self.device_selector.setMinimumWidth(180)
        self.device_selector.setMaximumWidth(300)
        self.device_selector.setToolTip("All manual actions target this exact ADB serial. Ctrl-select rows in Device Manager for multi-phone runs.")
        self.device_selector.currentIndexChanged.connect(self._select_device)
        header.addWidget(self.device_selector)
        self.command_button = button("Commands", window.command_palette)
        self.command_button.setToolTip("Search actions (Ctrl+Shift+P)")
        header.addWidget(self.command_button)
        self.preview_toggle = button("Preview", self.toggle_preview)
        self.preview_toggle.setToolTip("Show or hide the active phone preview on a compact window")
        header.addWidget(self.preview_toggle)
        self.emergency = button("Emergency stop", window.emergency_stop)
        self.emergency.setObjectName("emergency")
        self.emergency.setToolTip("Stop all script workers and block new studio inputs (Ctrl+Shift+F12)")
        header.addWidget(self.emergency)
        main.addLayout(header)
        self.simulation_notice = label(SIMULATION_LABEL, "notice")
        self.simulation_notice.hide()
        main.addWidget(self.simulation_notice)
        self.notification = label("", "notice")
        self.notification.hide()
        self.notification.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        main.addWidget(self.notification)
        self.stack = QStackedWidget()
        # Hidden workspaces must not impose their largest page's minimum on
        # the whole window. Visible pages reflow and compact previews on resize.
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.pages, self.preview_slots, self.execution_slots = {}, {}, {}
        self.splitters = {}
        self.project = ProjectExplorer(window)
        self.documents = ScriptTabs(window)
        studio = QWidget()
        studio_layout = QVBoxLayout(studio)
        studio_layout.setContentsMargins(0, 0, 0, 0)
        self.welcome = QWidget()
        welcome = QHBoxLayout(self.welcome)
        welcome.setContentsMargins(0, 0, 0, 0)
        welcome.addWidget(label("Start with a phone or a Python script. Your work stays local.", "notice"), stretch=1)
        welcome.addWidget(button("Connect a device", lambda: window.show_workspace("devices")))
        welcome.addWidget(button("Start Demo Session", window.start_demo, primary=True))
        welcome.addWidget(button("New script", window.new_script))
        studio_layout.addWidget(self.welcome)
        split = QSplitter()
        split.addWidget(self.project)
        split.addWidget(self.documents)
        self.preview_slots["studio"] = self.slot()
        split.addWidget(self.preview_slots["studio"])
        split.setSizes([210, 650, 290])
        split.setStretchFactor(1, 1)
        self.splitters["studio_horizontal"] = split
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(split)
        self.execution_slots["studio"] = self.slot()
        vertical.addWidget(self.execution_slots["studio"])
        vertical.setSizes([620, 180])
        vertical.setStretchFactor(0, 1)
        self.splitters["studio_vertical"] = vertical
        studio_layout.addWidget(vertical, stretch=1)
        self._page("studio", studio)
        for key, widget in (("devices", window.docks["devices"]), ("visual", window.docks["visual"]),
                            ("recorder", window.docks["recorder"])):
            split = QSplitter()
            split.setChildrenCollapsible(False)
            split.addWidget(widget)
            slot = self.slot()
            self.preview_slots[key] = slot
            split.addWidget(slot)
            split.setSizes([900, 300])
            split.setStretchFactor(0, 1)
            self.splitters[key] = split
            self._page(key, split)
        monitor = QWidget()
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics = label("Host metrics: collecting…", "notice")
        monitor_layout.addWidget(self.metrics)
        actions = QHBoxLayout()
        for text, operation in (("Pause selected run", "pause"), ("Resume selected run", "resume"), ("Stop selected run", "cancel")):
            actions.addWidget(button(text, lambda name=operation: window._control_run(name)))
        actions.addStretch()
        monitor_layout.addLayout(actions)
        self.execution_slots["monitor"] = self.slot()
        monitor_layout.addWidget(self.execution_slots["monitor"], stretch=1)
        self._page("monitor", monitor)
        tasks, task_layout = surface()
        task_layout.addWidget(label("Run today. Schedule later.", "workspaceTitle"))
        task_layout.addWidget(label("Task scheduling and automatic recovery are not implemented in this alpha. No background task is created from this page.", "notice"))
        task_layout.addWidget(button("Open script assignments", lambda: window.show_workspace("devices"), primary=True))
        task_layout.addWidget(label("Use Device Manager to select phones. Execution → Assign Python file assigns a script to the current phone. Run assigned files starts independent trusted workers on selected phones."))
        task_layout.addStretch()
        self._page("tasks", tasks)
        self.settings_panel = SettingsPanel(window.settings)
        self.settings_panel.apply_requested.connect(window.apply_settings)
        self._page("settings", self.settings_panel)
        main.addWidget(self.stack, stretch=1)
        layout.addLayout(main, stretch=1)
        self.switch("studio")
        self.project.refresh()
        for name, splitter in self.splitters.items():
            saved = window.settings.value("workspace_v2/" + name)
            if saved:
                splitter.restoreState(saved)
        self._responsive_layout()

    @staticmethod
    def slot():
        widget = QWidget()
        widget.setMinimumWidth(280)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        return widget

    def _page(self, key, widget):
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def switch(self, key):
        if key not in self.pages:
            return
        if key != self.current and key in ("devices", "visual", "recorder"):
            self.preview_on_small = False
        self.current = key
        self.stack.setCurrentWidget(self.pages[key])
        self.title.setText(WORKSPACES[key][0])
        self.subtitle.setText(WORKSPACES[key][1])
        for name, nav in self.nav.items():
            nav.setChecked(name == key)
        if key in self.preview_slots:
            self.preview_slots[key].layout().addWidget(self.window.docks["phone"])
            self.window.docks["phone"].show()
        execution_key = "monitor" if key == "monitor" else "studio"
        self.execution_slots[execution_key].layout().addWidget(self.window.docks["events"])
        self.window.docks["events"].show()
        if key in self.window.docks:
            self.window.docks[key].show()
        self.notification.hide()
        self._responsive_layout()

    def toggle_sidebar(self):
        self.user_collapsed = not self.user_collapsed
        self.window.settings.setValue("sidebar_collapsed", self.user_collapsed)
        self._responsive_layout()

    def _responsive_layout(self):
        collapsed = self.user_collapsed or self.width() < 1050
        self.sidebar.setFixedWidth(64 if collapsed else 190)
        self.brand.setText("A" if collapsed else "ANDROID\nAUTOMATION")
        self.alpha.setVisible(not collapsed)
        self.local_label.setVisible(not collapsed)
        self.collapse.setText("»" if collapsed else "Collapse sidebar")
        for nav in self.nav.values():
            nav.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if collapsed else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        compact = self.width() < 1250
        for slot in self.preview_slots.values():
            slot.setVisible(not compact or self.preview_on_small)
        # Dense tool forms and a phone cannot both fit a compact pane. The
        # header toggle shows either the tools or the preview at full width.
        for key in ("devices", "visual", "recorder"):
            self.window.docks[key].setVisible(not compact or not self.preview_on_small)
        self.project.setVisible(self.width() >= 1100)
        self.preview_toggle.setVisible(compact and self.current in self.preview_slots)
        self.preview_toggle.setText("Back to tools" if compact and self.preview_on_small and self.current in ("devices", "visual", "recorder") else "Preview")

    def toggle_preview(self):
        self.preview_on_small = not self.preview_on_small
        self._responsive_layout()

    def reveal_preview(self):
        self.preview_on_small = True
        self._responsive_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview_toggle") and hasattr(self, "project"):
            self._responsive_layout()

    def sync_devices(self):
        observed = self.window.registry.snapshot()
        selected = self.window._selected_identity()
        simulated = self.window.simulations.snapshot()
        signature = (selected, tuple((d.serial, d.state, d.model) for d in observed), tuple((d.serial, d.generation, d.available) for d in simulated))
        if signature == self._selector_signature:
            return
        self._selector_signature = signature
        blocker = QSignalBlocker(self.device_selector)
        self.device_selector.clear()
        self.device_selector.addItem("Choose a phone", None)
        for device in observed:
            self.device_selector.addItem(f"{device.model or device.serial} · {'connected' if device.available else device.state}", device.serial)
            self.device_selector.setItemData(self.device_selector.count() - 1, device.serial, Qt.ItemDataRole.ToolTipRole)
        if simulated:
            self.device_selector.insertSeparator(self.device_selector.count())
            for info in simulated:
                self.device_selector.addItem(info.name + " · SIMULATED" + (" (stopped)" if not info.available else ""), info.serial)
                self.device_selector.setItemData(self.device_selector.count()-1, SIMULATION_LABEL, Qt.ItemDataRole.ToolTipRole)
        self.device_selector.setCurrentIndex(max(0, self.device_selector.findData(selected)))
        del blocker

    def _select_device(self, index):
        serial = self.device_selector.itemData(index)
        if is_simulation(serial):
            self.window.select_simulation(serial)
        else:
            self.window.select_real_device(serial)

    def save(self):
        self.window.settings.setValue("last_workspace", self.current)
        for name, splitter in self.splitters.items():
            self.window.settings.setValue("workspace_v2/" + name, splitter.saveState())

    def reset(self):
        self.splitters["studio_horizontal"].setSizes([210, 650, 290])
        self.splitters["studio_vertical"].setSizes([620, 180])
        for key in ("devices", "visual", "recorder"):
            self.splitters[key].setSizes([900, 300])
        self.switch("studio")
