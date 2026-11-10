"""Visible approved-studio controls, replacing the retired sidebar journey."""
import os

import pytest
from PySide6.QtWidgets import QApplication

from app.ui.window import StudioWindow


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires Qt GUI")
def test_approved_studio_controls_and_responsive_layout():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(discover=False)
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    shell = window.shell
    assert shell.current == "studio"
    assert not shell.sidebar.isVisible()
    assert not shell.project.isVisible()
    assert all(not window.docks[name].isVisible() for name in ("visual", "recorder"))
    assert all(getattr(shell, name).isVisible() for name in (
        "start_button", "stop_button", "pause_button", "coordinate_button", "screenshot_button", "settings_button"))
    assert len(shell.studio_split.sizes()) == 2
    assert 0.40 <= shell.studio_split.sizes()[0] / sum(shell.studio_split.sizes()) <= 0.50
    window.resize(1050, 720)
    app.processEvents()
    assert shell.preview_slots["studio"].isVisible()
    assert all(not window.docks[name].isVisible() for name in ("visual", "recorder"))
    shell.toggle_console()
    assert not shell.execution_slots["studio"].isVisible()
    shell.toggle_console()
    assert shell.execution_slots["studio"].isVisible()
    window.close()
