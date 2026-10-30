"""Real Qt widgets and explicit RGB/PNG fixtures; no physical phone claim."""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.streaming.capture import ScreenFrame
from app.ui.preview import PhonePreview
from app.vision.matching import Match, Region


@dataclass(frozen=True)
class FixtureFrame:
    serial: str
    rgb: bytes
    width: int
    height: int
    source_width: int | None
    source_height: int | None
    captured_at: float
    sequence: int
    orientation: int | None = None


def spin(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(5)
    raise AssertionError("Timed out waiting for Qt state")


def video(width=100, height=200, source_width=1000, source_height=2000, sequence=1):
    return FixtureFrame("fixture-phone", bytes((17, 89, 201)) * width * height,
                        width, height, source_width, source_height,
                        time.monotonic(), sequence)


def main():
    app = QApplication([])
    app.setDoubleClickInterval(60)
    preview = PhonePreview()
    preview.resize(500, 500)
    preview.show()
    app.processEvents()
    frame = video()
    preview.set_video_frame(frame)
    app.processEvents()
    assert preview.image.width() == 100 and preview.image.height() == 200
    assert preview.image.pixelColor(30, 50).getRgb() == (17, 89, 201, 255)
    assert preview._pixel_buffer is frame.rgb
    assert preview.grab().width() == preview.width()
    gestures, doubles, coordinates = [], [], []
    preview.gesture.connect(lambda start, end, duration: gestures.append((start, end, duration)))
    preview.double_tap.connect(lambda x, y: doubles.append((x, y)))
    preview.coordinate.connect(lambda x, y: coordinates.append((x, y)))
    # Coordinates are full device pixels even though only 100x200 video pixels
    # are decoded. Avoid pixel edges so integer Qt pointer rounding is stable.
    point = QPoint(*map(round, preview.viewport().from_device(501, 1001)))
    QTest.mouseMove(preview, point)
    expected = preview.viewport().to_device(point.x(), point.y())
    assert expected[0] >= 490 and expected[1] >= 990
    assert coordinates[-1] == expected
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    assert not gestures
    # Ordinary video updates must not cancel a pending point tap.
    preview.set_video_frame(replace(frame, sequence=2))
    spin(app, lambda: len(gestures) == 1)
    assert gestures[0][:2] == (expected, expected)
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=QPoint(20, 100))
    QTest.qWait(100)
    assert len(gestures) == 1

    # Simulate the Qt event sequence for an actual double click: the first
    # release starts a pending tap, then MouseButtonDblClick cancels it.
    gestures.clear()
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseDClick(preview, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
    QTest.qWait(100)
    assert not gestures and doubles == [expected]

    # Long press and swipe preserve duration and original-device endpoints.
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
    preview._pressed_at = time.monotonic() - 0.9
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
    assert gestures[-1][:2] == (expected, expected) and gestures[-1][2] >= 850
    end = QPoint(*map(round, preview.viewport().from_device(501, 401)))
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
    preview._pressed_at = time.monotonic() - 0.7
    QTest.mouseMove(preview, end)
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=end)
    assert gestures[-1][0] == expected
    assert gestures[-1][1] == preview.viewport().to_device(end.x(), end.y())
    assert gestures[-1][2] >= 650

    # A changed resolution, serial, restart or widget transform invalidates all
    # gestures made in the old coordinate space, including deferred taps.
    baseline = len(gestures)
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    preview.set_video_frame(video(200, 100, 2000, 1000, sequence=3))
    QTest.qWait(100)
    assert len(gestures) == baseline
    point = QPoint(*map(round, preview.viewport().from_device(1001, 501)))
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
    preview.set_video_frame(replace(preview.frame, serial="fixture-other", sequence=4))
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
    assert len(gestures) == baseline
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    preview.cancel_input()
    QTest.qWait(100)
    assert len(gestures) == baseline
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    preview.resize(600, 500)
    QTest.qWait(100)
    assert len(gestures) == baseline
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    preview.set_video_frame(replace(preview.frame, sequence=1))
    QTest.qWait(100)
    assert len(gestures) == baseline

    # Orientation is already reflected in the decoded pixels. A half-turn must
    # still invalidate old pending/held inputs despite unchanged dimensions.
    preview.set_video_frame(replace(preview.frame, orientation=0, sequence=9))
    point = QPoint(*map(round, preview.viewport().from_device(1001, 501)))
    image_before_turn = preview.image.copy()
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
    preview.set_video_frame(replace(preview.frame, orientation=180, sequence=10))
    QTest.qWait(100)
    assert len(gestures) == baseline
    assert preview.image == image_before_turn
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
    assert preview._press is not None
    preview.set_video_frame(replace(preview.frame, orientation=0, sequence=11))
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
    assert len(gestures) == baseline and preview._press is None

    # Overlays never touch raw screenshot/video pixels used by recognition.
    before = bytes(preview.frame.rgb)
    image_before = preview.image.copy()
    preview.set_matches([Match(Region(100, 100, 200, 200), 0.95)])
    preview.grab()
    assert preview.frame.rgb == before and preview.image == image_before
    preview.set_video_frame(video(source_width=None, source_height=None, sequence=8))
    assert not preview.viewport().input_available and not preview.image.isNull()
    preview.grab()
    try:
        preview.set_video_frame(replace(video(), rgb=b"bad"))
    except ValueError:
        pass
    else:
        raise AssertionError("Malformed RGB bytes accepted")

    # Preserve actual PNG fallback and coordinate contract.
    data = QByteArray()
    buffer = QBuffer(data)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image = QImage(100, 200, QImage.Format.Format_RGB888)
    image.fill(Qt.GlobalColor.blue)
    assert image.save(buffer, "PNG")
    preview.set_frame(ScreenFrame("fixture-png", bytes(data), 100, 200, time.monotonic()))
    assert preview.viewport().source_width == 100
    assert preview.image.pixelColor(1, 1).blue() == 255
    preview.clear()
    assert preview.frame is None and preview.image.isNull()
    preview.close()
    print(json.dumps({"rgb": True, "scaled_coordinates": True, "single_double_tap": True,
                      "long_swipe": True, "invalidation": True, "overlays": True}))


if __name__ == "__main__":
    main()
