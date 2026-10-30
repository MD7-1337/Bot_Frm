"""Native frame rendering and coordinate-safe gestures, without device I/O.

Video input is packed immutable RGB, not a PNG screenshot emulating a stream.
Encoded pixels and original Android input coordinates have separate geometry.
Overlays are painted on the widget and never modify the captured pixels.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
import math
import time
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from app.streaming.capture import ScreenFrame
from app.streaming.coordinates import Viewport


@dataclass(frozen=True)
class PreviewViewport:
    """Fit encoded pixels, while mapping pointer input to original device pixels.

    Codec alignment can slightly alter the encoded aspect ratio. Rendering keeps
    that actual aspect ratio; input scales within the same content rectangle.
    Unknown or materially mismatched source geometry disables device input.
    """

    encoded_width: int
    encoded_height: int
    viewport_width: int
    viewport_height: int
    source_width: int | None
    source_height: int | None

    def __post_init__(self):
        _dimensions(self.encoded_width, self.encoded_height)
        Viewport(self.encoded_width, self.encoded_height,
                 self.viewport_width, self.viewport_height)
        if (self.source_width, self.source_height) != (None, None):
            _dimensions(self.source_width, self.source_height)

    @property
    def content_rect(self) -> tuple[float, float, float, float]:
        return Viewport(self.encoded_width, self.encoded_height,
                        self.viewport_width, self.viewport_height).content_rect

    @property
    def input_available(self) -> bool:
        if self.source_width is None or self.source_height is None:
            return False
        # scrcpy rounds encoded dimensions to codec alignment. Permit at most
        # eight encoded pixels of aspect error; never map an obsolete rotation.
        cross_error = abs(self.encoded_width * self.source_height
                          - self.encoded_height * self.source_width)
        return cross_error <= 8 * max(self.source_width, self.source_height)

    def to_device(self, x: float, y: float) -> tuple[int, int] | None:
        if not self.input_available or not math.isfinite(x) or not math.isfinite(y):
            return None
        left, top, width, height = self.content_rect
        if not (left <= x < left + width and top <= y < top + height):
            return None
        return (min(self.source_width - 1, int((x - left) * self.source_width / width)),
                min(self.source_height - 1, int((y - top) * self.source_height / height)))

    def from_device(self, x: int, y: int) -> tuple[float, float]:
        if (not self.input_available or type(x) is not int or type(y) is not int
                or not 0 <= x < self.source_width or not 0 <= y < self.source_height):
            raise ValueError("Device coordinates are unavailable or outside the source screen")
        left, top, width, height = self.content_rect
        return (left + (x + 0.5) * width / self.source_width,
                top + (y + 0.5) * height / self.source_height)


def _dimensions(width: Any, height: Any) -> None:
    if (type(width) is not int or type(height) is not int
            or not 0 < width <= 16_384 or not 0 < height <= 16_384
            or width * height > 100_000_000):
        raise ValueError("Frame dimensions are invalid or unsupported")


class PhonePreview(QWidget):
    # Point gestures shorter than 500 ms are delayed through Qt's double-click
    # interval. Consumers receive one single tap OR one double_tap, never three.
    gesture = Signal(object, object, int)
    double_tap = Signal(int, int)
    coordinate = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(230, 320)
        self.setMouseTracking(True)
        self.image = QImage()
        self.frame: Any = None
        self._pixel_buffer: bytes | None = None
        self._source_size: tuple[int | None, int | None] = (None, None)
        self._signature = None
        self._input_epoch = 0
        self._press = None
        self._pressed_at = 0.0
        self._double_release = False
        self._pending_single = None
        self._matches: list[Any] = []
        self._tap_timer = QTimer(self)
        self._tap_timer.setSingleShot(True)
        self._tap_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tap_timer.timeout.connect(self._dispatch_single)
        self.setToolTip("Select an authorized device to preview and control it")

    def _cancel_input(self):
        self._input_epoch += 1
        self._press = None
        self._double_release = False
        self._pending_single = None
        self._tap_timer.stop()

    def cancel_input(self):
        """Invalidate held/deferred gestures on emergency stop or lease changes."""
        self._cancel_input()

    def _accept_frame(self, frame, image: QImage, source_size, *, video: bool):
        if (not isinstance(frame.serial, str) or not frame.serial
                or isinstance(frame.captured_at, bool)
                or not isinstance(frame.captured_at, (int, float))
                or not math.isfinite(frame.captured_at)):
            raise ValueError("Frame identity or timestamp is invalid")
        orientation = getattr(frame, "orientation", None)
        if orientation is not None and (type(orientation) is not int
                                        or orientation not in (0, 90, 180, 270)):
            raise ValueError("Observed frame orientation must be degrees or unavailable")
        # Pixels already have the device's current orientation. Metadata only
        # invalidates old inputs, including a 180-degree turn with equal size.
        signature = (frame.serial, frame.width, frame.height, *source_size,
                     orientation, video)
        restarted = (video and self.frame is not None
                     and hasattr(self.frame, "sequence")
                     and frame.sequence <= self.frame.sequence)
        if signature != self._signature or restarted:
            self._cancel_input()
            self._matches = []
        self._signature = signature
        self._source_size = source_size
        self.image = image
        self.frame = frame
        self.setToolTip("Live scrcpy video · tap, double tap, hold or drag" if video
                        else "ADB screenshot fallback · tap, double tap, hold or drag")
        self.update()

    def set_frame(self, frame: ScreenFrame):
        """Set an actual full-device PNG screenshot, retaining the fallback API."""
        _dimensions(frame.width, frame.height)
        image = QImage.fromData(frame.png, "PNG")
        if image.isNull() or image.width() != frame.width or image.height() != frame.height:
            raise ValueError("Screenshot PNG could not be decoded")
        self._pixel_buffer = None
        self._accept_frame(frame, image, (frame.width, frame.height), video=False)

    def set_video_frame(self, frame):
        """Display an immutable packed RGB VideoFrame without PNG recompression.

        The source buffer remains retained for the QImage lifetime. Unknown
        original dimensions allow viewing but disable coordinate-based control.
        """
        _dimensions(frame.width, frame.height)
        if not isinstance(frame.rgb, bytes) or len(frame.rgb) != frame.width * frame.height * 3:
            raise ValueError("Video frame must contain exact immutable packed RGB bytes")
        source_size = (frame.source_width, frame.source_height)
        if source_size != (None, None):
            _dimensions(*source_size)
        if type(frame.sequence) is not int or frame.sequence < 0:
            raise ValueError("Video frame sequence must be a nonnegative integer")
        image = QImage(frame.rgb, frame.width, frame.height, frame.width * 3,
                       QImage.Format.Format_RGB888)
        if image.isNull():
            raise ValueError("Video RGB frame could not be rendered")
        self._pixel_buffer = frame.rgb
        self._accept_frame(frame, image, source_size, video=True)

    def clear(self):
        self._cancel_input()
        self.frame = None
        self.image = QImage()
        self._pixel_buffer = None
        self._source_size = (None, None)
        self._signature = None
        self._matches = []
        self.update()

    def viewport(self) -> PreviewViewport | None:
        if self.image.isNull() or self.width() <= 0 or self.height() <= 0:
            return None
        return PreviewViewport(self.image.width(), self.image.height(), self.width(),
                               self.height(), *self._source_size)

    def set_matches(self, matches):
        """Show bounded recognition overlays in original Android coordinates."""
        self._matches = list(islice(matches, 100))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#141a23"))
        viewport = self.viewport()
        if viewport:
            left, top, width, height = viewport.content_rect
            painter.drawImage(QRectF(left, top, width, height), self.image)
            if viewport.input_available:
                painter.setPen(QPen(QColor("#72e6ad"), 2))
                for match in self._matches:
                    region = match.region
                    if (region.x + region.width > viewport.source_width
                            or region.y + region.height > viewport.source_height):
                        continue
                    x = left + region.x * width / viewport.source_width
                    y = top + region.y * height / viewport.source_height
                    w = region.width * width / viewport.source_width
                    h = region.height * height / viewport.source_height
                    painter.drawRect(QRectF(x, y, w, h))
                    painter.drawText(QPointF(x + 3, max(top + 12, y - 4)), f"score {match.score:.3f}")
            else:
                painter.setPen(QColor("#ffc86b"))
                painter.drawText(QPointF(left + 8, top + 20), "Input unavailable: awaiting device geometry")
        else:
            painter.setPen(QColor("#aebbd0"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No device frame\nSelect an authorized device")

    def resizeEvent(self, event):
        # A press and release must use the same rendering transform.
        self._cancel_input()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        viewport = self.viewport()
        if event.button() == Qt.MouseButton.LeftButton and viewport:
            # A separate second click may be outside Qt's double-click radius;
            # preserve the first click before beginning a different gesture.
            if self._pending_single is not None:
                self._dispatch_single()
            self._press = viewport.to_device(event.position().x(), event.position().y())
            self._pressed_at = time.monotonic()
            self._double_release = False

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._double_release:
            self._double_release = False
            self._press = None
            return
        viewport = self.viewport()
        if viewport and self._press is not None:
            end = viewport.to_device(event.position().x(), event.position().y())
            if end is not None:
                duration = max(1, min(60_000, round((time.monotonic() - self._pressed_at) * 1000)))
                if self._press == end and duration < 500:
                    self._pending_single = (self._input_epoch, self._press, duration)
                    self._tap_timer.start(QApplication.doubleClickInterval())
                else:
                    self.gesture.emit(self._press, end, duration)
        self._press = None

    def mouseDoubleClickEvent(self, event):
        viewport = self.viewport()
        if event.button() == Qt.MouseButton.LeftButton and viewport:
            point = viewport.to_device(event.position().x(), event.position().y())
            if point is not None:
                self._tap_timer.stop()
                self._pending_single = None
                self._press = None
                self._double_release = True
                self.double_tap.emit(*point)

    def _dispatch_single(self):
        self._tap_timer.stop()
        pending, self._pending_single = self._pending_single, None
        if pending is not None:
            epoch, point, duration = pending
            if epoch == self._input_epoch and self.frame is not None:
                self.gesture.emit(point, point, duration)

    def mouseMoveEvent(self, event):
        viewport = self.viewport()
        if viewport:
            point = viewport.to_device(event.position().x(), event.position().y())
            if point is not None:
                self.coordinate.emit(*point)
