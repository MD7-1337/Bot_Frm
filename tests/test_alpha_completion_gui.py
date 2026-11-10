"""Inspector lifecycle in the approved studio layout.

Backend debugger, scheduler, recorder, and project coverage lives in their
respective non-navigation test modules.
"""
import os

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.ui.coordinate_inspector import CoordinateInspector
from app.ui.window import StudioWindow


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires Qt GUI")
def test_coordinate_inspector_resize_cancel_and_restore():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(discover=False)
    window.resize(1400, 850)
    window.show()
    app.processEvents()
    image = QImage(108, 240, QImage.Format.Format_RGB32)
    image.fill(0xff203040)
    inspector = CoordinateInspector(image, "fixture", source_size=(216, 480))
    inspector.exit_requested.connect(window.shell.close_coordinate_inspector)
    window.shell.show_coordinate_inspector(inspector)
    app.processEvents()
    inspector.select_point(27, 60)
    assert inspector.point == (54, 120)
    window.resize(1000, 700)
    app.processEvents()
    assert inspector.isVisible()
    inspector.exit_requested.emit()
    app.processEvents()
    assert window.preview.isVisible()
    assert window.shell._coordinate_inspector is None
    window.close()
