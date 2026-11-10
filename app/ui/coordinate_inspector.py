"""Frozen Android coordinate picker embedded in the main editor/preview layout."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.projects.assets import android_region
from app.ui.capture_dialog import SelectionCanvas
from app.ui.components import button
from app.vision.matching import Region


class PointCanvas(SelectionCanvas):
    point_selected = Signal(int, int)

    def __init__(self, image, parent=None):
        super().__init__(image, parent)
        self.point = None
        self.setAccessibleName("Frozen Android coordinate screenshot")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = self._point(event.position())
            if point is not None:
                self.point = point
                self.point_selected.emit(*point)
                self.update()

    def mouseMoveEvent(self, event):
        self._emit_pixel(event.position())

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.point is None:
            return
        x, y = self.viewport().from_device(*self.point)
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#d4af37"), 1))
        painter.drawLine(int(x), 0, int(x), self.height())
        painter.drawLine(0, int(y), self.width(), int(y))
        painter.setPen(QPen(QColor("#eae0d0"), 2))
        painter.drawEllipse(int(x) - 5, int(y) - 5, 10, 10)


class CoordinateInspector(QWidget):
    insert_requested = Signal(str)
    exit_requested = Signal()

    def __init__(self, image, serial: str, source_size: tuple[int, int] | None = None, parent=None):
        super().__init__(parent)
        self.source_size = source_size or (image.width(), image.height())
        self.image_size = (image.width(), image.height())
        self.point = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        title = QLabel("◎  Coordinate Inspector Active")
        title.setObjectName("stitchHeading")
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(button("Exit (Esc)", self.exit_requested.emit))
        layout.addLayout(heading)
        metadata = QLabel(f"{serial}  |  Native: {self.source_size[0]} × {self.source_size[1]}  |  Frame Locked")
        metadata.setObjectName("stitchMetadata")
        layout.addWidget(metadata)
        self.canvas = PointCanvas(image)
        self.canvas.point_selected.connect(self.select_point)
        layout.addWidget(self.canvas, stretch=1)
        footer = QHBoxLayout()
        self.coordinates = QLabel("Click any point on the Android screen to capture")
        self.coordinates.setObjectName("stitchMetadata")
        footer.addWidget(self.coordinates, stretch=1)
        self.insert_button = button("Insert tap(x, y)", self.insert, primary=True)
        self.insert_button.setEnabled(False)
        footer.addWidget(self.insert_button)
        layout.addLayout(footer)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.exit_requested.emit)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self.insert)

    def select_point(self, x: int, y: int):
        mapped = android_region(Region(x, y, 1, 1), self.image_size, self.source_size)
        self.point = (mapped.x, mapped.y)
        self.coordinates.setText(f"Android Display: X: {mapped.x}, Y: {mapped.y}")
        self.insert_button.setText(f"Insert tap({mapped.x}, {mapped.y})")
        self.insert_button.setEnabled(True)

    def insert(self):
        if self.point is not None:
            self.insert_requested.emit(f"tap({self.point[0]}, {self.point[1]})\n")
