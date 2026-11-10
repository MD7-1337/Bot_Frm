"""Workspace-based IDE shell; existing services and widgets retain their owners."""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QSplitter, QStackedWidget,
                              QSizePolicy, QTabWidget, QToolButton, QVBoxLayout, QWidget)

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
    "tasks": ("Task Manager", "Approve source snapshots, schedule device queues and review durable history."),
    "settings": ("Settings", "A local setup that works for your computer and your devices."),
    "debugger": ("Debugger", "Inspect Python statements and variables in independent device workers."),
    "projects": ("Projects", "Create, search, back up and exchange your automation projects."),
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
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
        # The approved studio is one editor and one phone; legacy workspace
        # widgets stay owned by the window for compatibility, without navigation.
        self.sidebar.hide()
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(10, 6, 10, 6)
        header.setSpacing(6)
        self.stitch_header = QWidget()
        self.stitch_header.setObjectName("stitchHeader")
        self.stitch_header.setLayout(header)
        for caption, callback, glyph, primary in (
            ("Start", window.run_script, "run", True),
            ("Stop", lambda: window._control_run("cancel"), "stop", False),
            ("Pause / Resume", window.toggle_run_pause, "pause", False),
            ("Get Coordinate", window.get_coordinate, "search", False),
            ("Screenshot", window.capture_region, "visual", False),
        ):
            control = button(caption, callback, primary=primary)
            control.setIcon(icon(glyph, "#d4af37"))
            control.setAccessibleName(caption)
            header.addWidget(control)
            setattr(self, {"Start":"start_button", "Stop":"stop_button", "Pause / Resume":"pause_button",
                           "Get Coordinate":"coordinate_button", "Screenshot":"screenshot_button"}[caption], control)
        header.addStretch(1)
        self.device_selector = QComboBox()
        self.device_selector.setAccessibleName("Active Android device")
        self.device_selector.setMinimumWidth(180)
        self.device_selector.setMaximumWidth(300)
        self.device_selector.setToolTip("All manual actions target this exact ADB serial.")
        self.device_selector.currentIndexChanged.connect(self._select_device)
        header.addWidget(self.device_selector)
        self.settings_button = button("", lambda: window.show_workspace("settings"))
        self.settings_button.setIcon(icon("settings", "#d4af37"))
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")
        header.addWidget(self.settings_button)
        main.addWidget(self.stitch_header)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.title = label("Script Studio", "workspaceTitle")
        self.subtitle = label(WORKSPACES["studio"][1])
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        # Legacy workspace controls remain constructed for command/menu routing.
        self.command_button = button("Commands", window.command_palette)
        self.command_button.setToolTip("Search actions (Ctrl+Shift+P)")
        self.command_button.hide()
        self.preview_toggle = button("Preview", self.toggle_preview)
        self.preview_toggle.setToolTip("Show or hide the active phone preview on a compact window")
        self.preview_toggle.hide()
        self.emergency = button("Emergency stop", window.emergency_stop)
        self.emergency.setObjectName("emergency")
        self.emergency.setToolTip("Stop all script workers and block new studio inputs (Ctrl+Shift+F12)")
        sidebar.addWidget(self.emergency)
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
        self.project.setParent(self)
        self.project.hide()
        self.documents = ScriptTabs(window)
        # Monaco reflows to its viewport. Its preferred width (and long tab
        # names) must not force the splitter wider than the visible workspace,
        # pushing the phone pane beyond the right edge on Windows.
        self.documents.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.documents.setMinimumWidth(180)
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
        self.welcome.hide()
        split = QSplitter()
        split.setChildrenCollapsible(False)
        split.addWidget(self.documents)
        self.preview_slots["studio"] = self.slot()
        split.addWidget(self.preview_slots["studio"])
        split.setSizes([450, 550])
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        self.splitters["studio_horizontal"] = split
        self.studio_split = split
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(split)
        self.execution_slots["studio"] = self.slot()
        self.console_toggle = button("▾  Output Console", self.toggle_console)
        self.console_toggle.setObjectName("consoleHeader")
        console = QWidget()
        console_layout = QVBoxLayout(console)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(0)
        console_layout.addWidget(self.console_toggle)
        console_layout.addWidget(self.execution_slots["studio"], stretch=1)
        vertical.addWidget(console)
        # Match the compact Stitch console on first launch; users can drag
        # the splitter to enlarge it when reviewing long script output.
        vertical.setSizes([740, 90])
        vertical.setStretchFactor(0, 1)
        self.splitters["studio_vertical"] = vertical
        studio_layout.addWidget(vertical, stretch=1)
        self.welcome.hide()
        self._page("studio", studio)
        for key, widget in (("devices", window.docks["devices"]),):
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
        self.monitor_tabs = QTabWidget()
        self.monitor_tabs.addTab(self.execution_slots["monitor"], "Runs and output")
        self.monitor_tabs.addTab(window.recovery_panel, "Failure history")
        monitor_layout.addWidget(self.monitor_tabs, stretch=1)
        self._page("monitor", monitor)
        self._page("tasks", window.task_panel)
        debug = QSplitter(Qt.Orientation.Vertical)
        self.debug_editor_slot = self.slot()
        debug.addWidget(self.debug_editor_slot)
        debug.addWidget(window.debugger_panel)
        debug.setSizes([480, 300])
        debug.setStretchFactor(0, 1)
        self.splitters["debugger_vertical"] = debug
        # Backend panels remain alive for existing services, but are not pages.
        self.settings_panel = SettingsPanel(window.settings)
        self.settings_panel.apply_requested.connect(window.apply_settings)
        self._page("settings", self.settings_panel)
        main.addWidget(self.stack, stretch=1)
        layout.addLayout(main, stretch=1)
        self.switch("studio")
        for name in ("visual", "recorder"):
            window.docks[name].hide()
            window.docks[name].setParent(None)
            window.docks[name].setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.project.hide()
        self.welcome.hide()
        self.project.refresh()
        for name, splitter in self.splitters.items():
            saved = window.settings.value(("workspace_v3/" if name in ("studio_horizontal", "studio_vertical") else "workspace_v2/") + name)
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
        if key != "studio" and getattr(self, "_coordinate_inspector", None) is not None:
            self.close_coordinate_inspector()
        if key == "debugger":
            self.debug_editor_slot.layout().addWidget(self.documents)
        elif self.current == "debugger":
            self.studio_split.insertWidget(1, self.documents)
        if key != self.current and key in ("devices", "visual", "recorder"):
            self.preview_on_small = False
        self.current = key
        self.stitch_header.setVisible(key == "studio")
        self.window.live_panel.set_stitch_mode(key == "studio")
        self.window.execution_panel.set_compact(key == "studio")
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
        self.emergency.setText("STOP" if collapsed else "Emergency stop")
        for nav in self.nav.values():
            nav.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if collapsed else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        compact = self.width() < 1250
        for key, slot in self.preview_slots.items():
            if key != "studio":
                slot.setVisible(not compact or self.preview_on_small)
        # Dense tool forms and a phone cannot both fit a compact pane. The
        # header toggle shows either the tools or the preview at full width.
        # Only the Device Manager remains a visible secondary workspace.
        # Detached legacy Visual Tools/Recorder docks must not be re-shown
        # during a resize; they have no visible page in the approved design.
        self.window.docks["devices"].setVisible(self.current == "devices" and (not compact or not self.preview_on_small))
        self.sidebar.hide()
        self.project.hide()
        self.preview_slots["studio"].show()
        self.preview_toggle.setVisible(compact and self.current in ("devices", "visual", "recorder"))
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
            namespace = "workspace_v3/" if name in ("studio_horizontal", "studio_vertical") else "workspace_v2/"
            self.window.settings.setValue(namespace + name, splitter.saveState())

    def reset(self):
        self.splitters["studio_horizontal"].setSizes([450, 550])
        self.splitters["studio_vertical"].setSizes([740, 90])
        # The removed Visual Tools and Recorder pages no longer own splitters.
        # Reset only the layouts actually installed in this UI.
        self.splitters["devices"].setSizes([900, 300])
        self.switch("studio")

    def toggle_console(self):
        slot = self.execution_slots["studio"]
        slot.setVisible(not slot.isVisible())
        self.console_toggle.setText("▾  Output Console" if slot.isVisible() else "▸  Output Console")

    def show_coordinate_inspector(self, inspector):
        slot = self.preview_slots["studio"]
        self.window.docks["phone"].hide()
        slot.layout().addWidget(inspector)
        inspector.show()
        self._coordinate_inspector = inspector

    def close_coordinate_inspector(self):
        inspector = getattr(self, "_coordinate_inspector", None)
        if inspector is None:
            return
        self._coordinate_inspector = None
        self.preview_slots["studio"].layout().removeWidget(inspector)
        inspector.deleteLater()
        self.preview_slots["studio"].layout().addWidget(self.window.docks["phone"])
        self.window.docks["phone"].show()
