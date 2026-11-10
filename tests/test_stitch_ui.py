"""Exercise the two coordinate and command contracts added by the Stitch UI."""
import os
from pathlib import Path
import time

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.ui.capture_dialog import CaptureDialog
from app.ui.coordinate_inspector import CoordinateInspector
from app.vision.matching import Region

pytestmark = pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Requires an isolated Qt GUI run")


def _app():
    return QApplication.instance() or QApplication([])


def test_coordinate_inspector_uses_android_pixels_after_scaling():
    app = _app()
    for width, height in ((234, 108), (108, 234)):
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(0)
        picker = CoordinateInspector(image, "fixture")
        picker.canvas.resize(380, 220)
        location = (width * 3 // 4, height // 3)
        screen_point = picker.canvas.viewport().from_device(*location)
        assert picker.canvas._point(QPointF(*screen_point)) == location
        picker.select_point(*location)
        output = []
        picker.insert_requested.connect(output.append)
        picker.insert()
        assert output == [f"tap({location[0]}, {location[1]})\n"]
        picker.close()
    assert app is QApplication.instance()


def test_coordinate_inspector_maps_portrait_and_landscape_capture_sizes():
    _app()
    for width, height in ((240, 108), (108, 240)):
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(0)
        picker = CoordinateInspector(image, "fixture", source_size=(width * 2, height * 2))
        picker.canvas.resize(360, 250)
        point = (width // 3, height * 3 // 4)
        screen_point = picker.canvas.viewport().from_device(*point)
        assert picker.canvas._point(QPointF(*screen_point)) == point
        picker.select_point(*point)
        commands = []
        picker.insert_requested.connect(commands.append)
        picker.insert()
        assert commands == [f"tap({point[0] * 2}, {point[1] * 2})\n"]
        picker.close()


def test_capture_saves_png_and_inserts_supported_click_code(tmp_path: Path):
    app = _app()
    image = QImage(40, 30, QImage.Format.Format_RGB32)
    image.fill(0xffcc9933)
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    dialog = CaptureDialog(image, "fixture", save_directory=image_dir)
    dialog.select_region(Region(4, 5, 10, 7))
    dialog.filename.setText("play.png")
    commands = []
    dialog.command_ready.connect(commands.append)
    dialog.save_and_insert()
    assert commands == ['click("play.png")\n']
    assert QImage(str(image_dir / "play.png")).size() == image.copy(4, 5, 10, 7).size()

    custom = CaptureDialog(image, "fixture", save_directory=image_dir)
    custom.select_region(Region(2, 3, 8, 6))
    custom.filename.setText("special.png")
    custom.threshold.setValue(0.90)
    custom.command_ready.connect(commands.append)
    custom.save_and_insert()
    assert commands[-1] == 'click(Pattern("special.png").similar(0.90))\n'
    assert app is QApplication.instance()


def test_matching_uses_selected_original_or_fresh_frame(tmp_path: Path):
    app = _app()
    image = QImage(80, 60, QImage.Format.Format_RGB32)
    image.fill(0xff162030)
    for x in range(12, 29):
        for y in range(15, 30):
            image.setPixel(x, y, 0xffdcad40 if (x + y) % 3 else 0xff4e8175)
    captures = []

    def fresh():
        captures.append(True)
        return image.copy()

    dialog = CaptureDialog(image, "fixture", test_frame_provider=fresh,
                           save_directory=tmp_path)
    dialog.select_region(Region(12, 15, 17, 15))
    results = []
    dialog.match_finished.connect(results.append)

    def await_result():
        deadline = time.monotonic() + 8
        while not results and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert results, "Matching did not finish"
        assert results.pop()["matches"]
        assert dialog.tabs.currentWidget() is dialog.comparison

    dialog.match_source.setCurrentIndex(0)
    dialog.start_match()
    await_result()
    assert captures == []
    dialog.match_source.setCurrentIndex(1)
    dialog.start_match()
    await_result()
    assert captures == [True]
    dialog.close()
