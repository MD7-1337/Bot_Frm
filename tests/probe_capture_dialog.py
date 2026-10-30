"""Actual Qt interaction and OpenCV tests, with explicit synthetic screen input."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from app.ui.capture_dialog import CaptureDialog, image_rgb
from app.vision.matching import Region


def image(array):
    array = np.ascontiguousarray(array)
    return QImage(array.data, array.shape[1], array.shape[0], array.shape[1] * 3, QImage.Format.Format_RGB888).copy()


def spin(application, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        time.sleep(0.002)
    raise AssertionError("Capture operation timed out")


def main(directory):
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    rng = np.random.default_rng(42)
    pixels = rng.integers(0, 256, (50, 40, 3), dtype=np.uint8)
    original = image(pixels)
    # Qt row alignment is not necessarily a multiple of the logical RGB width.
    assert np.array_equal(image_rgb(image(pixels[:, :7])), pixels[:, :7])
    provider_threads = []
    provider_state = {"pixels": pixels.copy()}
    gate = threading.Event()
    gate.set()

    def provider():
        provider_threads.append(threading.get_ident())
        assert gate.wait(3)
        return image(provider_state["pixels"])

    dialog = CaptureDialog(original, "fixture-phone-one", (120, 150),
                           test_frame_provider=provider, script_directory=directory / "scripts")
    dialog.show()
    application.processEvents()
    canvas = dialog.canvas
    start = QPoint(*map(round, canvas.viewport().from_device(2, 3)))
    end = QPoint(*map(round, canvas.viewport().from_device(11, 14)))
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert dialog.selected_region == Region(2, 3, 10, 12), dialog.selected_region
    assert "x=6, y=9, width=30, height=36" in dialog.coordinates.text()
    assert np.array_equal(image_rgb(dialog.crop()), pixels[3:15, 2:12])
    assert np.array_equal(image_rgb(original), pixels)

    saved = []
    references = []
    dialog.asset_saved.connect(lambda path, region: saved.append((path, region)))
    dialog.reference_ready.connect(references.append)
    path = directory / 'quote" téléphone.png'
    old_dialog = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(path), "PNG (*.png)")
    try:
        QTest.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    finally:
        QFileDialog.getSaveFileName = old_dialog
    assert QImage(str(path)).size() == dialog.crop().size()
    assert np.array_equal(image_rgb(QImage(str(path))), pixels[3:15, 2:12])
    assert saved[0][1] == Region(6, 9, 30, 36)
    code = ast.parse(references[0])
    assert len(code.body) == 1
    assert ast.literal_eval(code.body[0].value) == '../quote" téléphone.png'
    try:
        dialog.save_to(directory / "missing" / "must-not-create.png")
    except OSError:
        pass
    else:
        raise AssertionError("Missing parent save unexpectedly succeeded")
    assert len(saved) == 1 and len(references) == 1

    results = []
    dialog.match_finished.connect(results.append)
    dialog.threshold.setValue(0.99)
    gate.clear()
    ticks = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    before = time.monotonic()
    dialog.start_match()
    assert time.monotonic() - before < .1
    spin(application, lambda: len(ticks) >= 3)
    assert dialog._busy
    gate.set()
    spin(application, lambda: len(results) == 1)
    assert results[-1]["error"] is None and len(results[-1]["matches"]) == 1
    assert "tap (21, 27)" in dialog.result.text(), dialog.result.text()
    assert provider_threads[-1] != threading.get_ident()

    # Match against another actual synthetic frame, preserving the frozen crop.
    fresh = pixels.copy()
    fresh[25:37, 20:30] = pixels[3:15, 2:12]
    provider_state["pixels"] = fresh
    dialog.start_match()
    spin(application, lambda: len(results) == 2)
    assert len(results[-1]["matches"]) == 2 and "Ambiguous" in dialog.result.text()
    assert np.array_equal(image_rgb(dialog.frame), pixels)
    assert np.array_equal(image_rgb(dialog.canvas.image), pixels)
    assert np.array_equal(image_rgb(dialog.crop()), pixels[3:15, 2:12])

    provider_state["pixels"] = rng.integers(0, 256, pixels.shape, dtype=np.uint8)
    dialog.start_match()
    spin(application, lambda: len(results) == 3)
    assert results[-1]["matches"] == [] and "No match" in dialog.result.text()

    provider_state["pixels"] = np.zeros((20, 20, 3), dtype=np.uint8)
    dialog.start_match()
    spin(application, lambda: len(results) == 4)
    assert "changed" in results[-1]["error"]
    assert not dialog.tabs.isTabEnabled(1), "Stale successful overlays survived a failed match"
    timer.stop()
    dialog.reject()
    assert not dialog.isVisible()

    unavailable = CaptureDialog(original, "fixture-phone-one")
    unavailable.select_region(Region(1, 1, 2, 2))
    assert not unavailable.test_button.isEnabled()
    unavailable.start_match()
    assert "unavailable" in unavailable.result.text()
    unavailable.reject()

    idle_close = CaptureDialog(original, "fixture-phone-one")
    completions = []
    idle_close.finished.connect(completions.append)
    idle_close.show()
    idle_close.close()
    application.processEvents()
    assert len(completions) == 1 and not idle_close.isVisible()

    # Degenerate templates fail explicitly, rather than produce fake matches.
    flat_pixels = np.zeros_like(pixels)
    flat = CaptureDialog(image(flat_pixels), "fixture-phone-one", test_frame_provider=lambda: original.copy())
    flat.select_region(Region(1, 1, 3, 3))
    flat_results = []
    flat.match_finished.connect(flat_results.append)
    flat.start_match()
    spin(application, lambda: bool(flat_results))
    assert "constant" in flat_results[0]["error"] and "Match failed" in flat.result.text()
    flat.reject()

    try:
        CaptureDialog(original, "fixture-phone-one", ())
    except ValueError:
        pass
    else:
        raise AssertionError("Malformed original device dimensions accepted")

    # Closing a live capture job never destroys a running QThreadPool or blocks
    # Qt event handling; the dialog closes after the bounded provider completes.
    closing = CaptureDialog(original, "fixture-phone-one", test_frame_provider=provider)
    closing.select_region(Region(1, 1, 5, 5))
    closing.show()
    gate.clear()
    provider_state["pixels"] = pixels
    closing.start_match()
    before = time.monotonic()
    closing.reject()
    assert time.monotonic() - before < .1 and closing._closing and closing._busy
    gate.set()
    spin(application, lambda: not closing._busy)
    assert not closing.isVisible()
    print(json.dumps({check: True for check in ("selection", "save", "reference", "match", "ambiguous",
                                               "no_match", "errors", "async", "frozen")}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
