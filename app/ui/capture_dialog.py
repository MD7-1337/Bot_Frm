"""Frozen screenshot selection, atomic asset saves, and asynchronous match tests.

No device controls are dispatched here. The provider is bound by the host to the
selected serial and must enforce its own finite capture timeout and generation.
"""
from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import (QIODevice, QObject, QPointF, QRectF, QRunnable,
                            QSaveFile, QThreadPool, Qt, Signal, Slot)
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from app.projects.assets import android_region, reference_code
from app.streaming.coordinates import Viewport
from app.vision.matching import Match, Region, find_scaled, validate_scales


def image_rgb(image: QImage) -> np.ndarray:
    """Copy logical RGB pixels, respecting Qt's row alignment and ownership."""
    if not isinstance(image, QImage) or image.isNull():
        raise ValueError("A decoded screenshot is required")
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    rows = np.frombuffer(image.constBits(), dtype=np.uint8,
                         count=image.bytesPerLine() * image.height()).reshape(image.height(), image.bytesPerLine())
    return rows[:, :image.width() * 3].reshape(image.height(), image.width(), 3).copy()


class SelectionCanvas(QWidget):
    selected = Signal(object)
    pixel_hovered = Signal(int, int, object)

    def __init__(self, image: QImage, parent: QWidget | None = None):
        super().__init__(parent)
        if image.isNull():
            raise ValueError("A decoded screenshot is required")
        self.image = image.copy()
        self.selection: Region | None = None
        self.matches: list[Match] = []
        self._anchor: tuple[int, int] | None = None
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setAccessibleName("Screenshot region selection")
        self.setToolTip("Drag within the screenshot to select a crop. Letterbox margins are excluded.")

    def viewport(self) -> Viewport:
        return Viewport(self.image.width(), self.image.height(), max(1, self.width()), max(1, self.height()))

    def set_selection(self, region: Region) -> None:
        # Also validates the bounds and argument type before changing state.
        android_region(region, (self.image.width(), self.image.height()), (self.image.width(), self.image.height()))
        self.selection = region
        self.matches = []
        self.selected.emit(region)
        self.update()

    def _point(self, position: QPointF, *, clamp: bool = False) -> tuple[int, int] | None:
        viewport = self.viewport()
        point = viewport.to_device(position.x(), position.y())
        if point is None and clamp:
            left, top, width, height = viewport.content_rect
            x = min(max(position.x(), left), left + width - 1e-6)
            y = min(max(position.y(), top), top + height - 1e-6)
            point = viewport.to_device(x, y)
        return point

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._anchor = self._point(event.position())
            self._emit_pixel(event.position())

    def mouseMoveEvent(self, event):
        self._emit_pixel(event.position())
        if self._anchor is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._extend(event.position())

    def _emit_pixel(self, position):
        point = self._point(position)
        if point is not None:
            x,y = point
            color = self.image.pixelColor(x,y)
            self.pixel_hovered.emit(x,y,(color.red(),color.green(),color.blue()))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._anchor is not None:
            self._extend(event.position())
            self._anchor = None

    def _extend(self, position):
        point = self._point(position, clamp=True)
        if point is not None and self._anchor is not None:
            x1, y1 = self._anchor
            x2, y2 = point
            self.set_selection(Region(min(x1, x2), min(y1, y2), abs(x2 - x1) + 1, abs(y2 - y1) + 1))

    def _rectangle(self, region: Region) -> QRectF:
        viewport = self.viewport()
        left, top, _, _ = viewport.content_rect
        return QRectF(left + region.x * viewport.scale, top + region.y * viewport.scale,
                      region.width * viewport.scale, region.height * viewport.scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#110d0c"))
        painter.drawImage(QRectF(*self.viewport().content_rect), self.image)
        if self.selection:
            painter.setPen(QPen(QColor("#d4af37"), 2))
            painter.setBrush(QColor(212, 175, 55, 45))
            painter.drawRect(self._rectangle(self.selection))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#69db99"), 2))
        for match in self.matches:
            rectangle = self._rectangle(match.region)
            painter.drawRect(rectangle)
            painter.drawText(rectangle.topLeft() + QPointF(2, 14), f"score {match.score:.3f}")


class _MatchSignals(QObject):
    done = Signal(object, object)


class _MatchJob(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _MatchSignals()

    def run(self):
        try:
            self.signals.done.emit(self.operation(), None)
        except Exception as error:
            self.signals.done.emit(None, str(error))


class CaptureDialog(QDialog):
    """Select/crop one frozen device frame and test it against a fresh frame.

    ``source_size`` contains original Android dimensions in the frame's current
    orientation, which may differ from the encoded frame's scaled dimensions.
    The provider executes off the GUI thread and returns a fresh, owned QImage.
    Changes in encoded dimensions require recapture rather than guessed scaling.
    """
    asset_saved = Signal(str, object)
    reference_ready = Signal(str)
    command_ready = Signal(str)
    match_finished = Signal(object)

    def __init__(self, frame: QImage, serial: str, source_size: tuple[int, int] | None = None,
                 parent: QWidget | None = None, *, test_frame_provider: Callable[[], QImage] | None = None,
                 script_directory: Path | None = None, save_directory: Path | None = None,
                 template_image: QImage | None = None):
        super().__init__(parent)
        if not isinstance(frame, QImage) or frame.isNull():
            raise ValueError("Capture requires a valid decoded frame")
        if not isinstance(serial, str) or not serial:
            raise ValueError("Capture requires the selected device serial")
        self.serial = serial
        self.source_size = source_size if source_size is not None else (frame.width(), frame.height())
        android_region(Region(0, 0, frame.width(), frame.height()),
                       (frame.width(), frame.height()), self.source_size)
        self.frame = frame.copy()
        if template_image is not None and template_image.isNull():
            raise ValueError("Match testing requires a decoded template")
        self.template_image = template_image.copy() if template_image is not None else None
        self.test_frame_provider = test_frame_provider
        self.script_directory = script_directory
        self.save_directory = save_directory
        self._busy = False
        self._closing = False
        self._job = None
        self._match_threshold = 0.85
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.setWindowTitle(f"Screenshot & Template Matching · {serial}")
        self.resize(1160, 760)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        self.instructions = QLabel("Fresh device frame captured  •  Drag a rectangle on the screenshot to select a target")
        self.instructions.setWordWrap(True)
        if serial.startswith("sim://"):
            self.instructions.setText("SIMULATED DEVICE — NOT CONNECTED TO ANDROID HARDWARE\nFrozen simulation pixels. Drag a crop; coordinates use the original simulated screen.")
        layout.addWidget(self.instructions)
        body = QHBoxLayout()
        body.setSpacing(10)
        left = QVBoxLayout()
        right = QVBoxLayout()
        self.canvas = SelectionCanvas(self.frame)
        self.canvas.selected.connect(self._selection_changed)
        self.comparison = SelectionCanvas(self.frame)
        self.comparison.setEnabled(False)
        self.comparison.setAccessibleName("Fresh-frame match results")
        self.tabs = QTabWidget()
        self.tabs.addTab(self.canvas, "Frozen capture · crop source")
        self.tabs.addTab(self.comparison, "Fresh match result")
        self.tabs.setTabEnabled(1, False)
        left.addWidget(self.tabs, stretch=1)
        self.coordinates = QLabel("No region selected")
        self.coordinates.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        left.addWidget(self.coordinates)
        body.addLayout(left, stretch=3)
        options = QWidget()
        options.setMinimumWidth(310)
        options.setMaximumWidth(380)
        options.setLayout(right)
        body.addWidget(options, stretch=1)
        layout.addLayout(body, stretch=1)
        heading = QLabel("Target Asset")
        heading.setObjectName("stitchHeading")
        right.addWidget(heading)
        right.addWidget(QLabel("Target Filename"))
        self.filename = QLineEdit("target.png")
        self.filename.setAccessibleName("Target filename")
        self.filename.textChanged.connect(self._update_code_preview)
        right.addWidget(self.filename)
        right.addWidget(QLabel("Similarity Score"))
        controls = QHBoxLayout()
        self.save_button = QPushButton("Save crop + insert reference…")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._choose_save)
        controls.addWidget(self.save_button)
        controls.addWidget(QLabel("Minimum score"))
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 1)
        self.threshold.setSingleStep(0.01)
        self.threshold.setDecimals(2)
        self.threshold.setValue(0.85)
        self.threshold.setToolTip("Normalized matching score; not a probability of correctness.")
        self.threshold.valueChanged.connect(self._update_code_preview)
        controls.addWidget(self.threshold)
        self.test_button = QPushButton("Test Matching")
        self.test_button.setEnabled(False)
        self.test_button.clicked.connect(self.start_match)
        controls.addWidget(self.test_button)
        # Keep the existing explicit Save As path for scripts outside a project.
        right.addWidget(self.save_button)
        right.addWidget(self.threshold)
        right.addWidget(QLabel("Test Matching"))
        self.match_source = QComboBox()
        self.match_source.addItems(["Original Screenshot", "New from Phone"])
        self.match_source.setCurrentIndex(0 if save_directory is not None else 1)
        right.addWidget(self.match_source)
        right.addWidget(self.test_button)
        search_controls = QHBoxLayout()
        self.scales = QLineEdit("1.0")
        self.scales.setMaxLength(256)
        self.scales.setToolTip("Explicit template scales: 0.75, 1, 1.25 (1–16 values between 0.1 and 4)")
        search_controls.addWidget(QLabel("Template scales"))
        search_controls.addWidget(self.scales)
        self.preprocessing = QComboBox()
        self.preprocessing.addItems(["none", "grayscale", "threshold", "edges"])
        search_controls.addWidget(self.preprocessing)
        self.search_selection = QCheckBox("Search only selected rectangle")
        search_controls.addWidget(self.search_selection)
        self.scales.hide()
        self.preprocessing.hide()
        self.search_selection.hide()
        self.result = QLabel("Select a region to save or test.")
        self.result.setWordWrap(True)
        self.result.setMinimumHeight(72)
        self.result.setAlignment(Qt.AlignmentFlag.AlignTop)
        if test_frame_provider is None and self.match_source.currentIndex() == 1:
            self.result.setText("Fresh-frame matching unavailable: no selected-device capture provider was supplied.")
        right.addWidget(self.result)
        self.back_button = QPushButton("Back to Selection (Preserve Crop)")
        self.back_button.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        right.addWidget(self.back_button)
        right.addWidget(QLabel("Code Generation Preview"))
        self.code_preview = QLabel()
        self.code_preview.setObjectName("stitchMetadata")
        self.code_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.code_preview)
        self._update_code_preview()
        right.addStretch()
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.save_insert_button = QPushButton("Save & Insert")
        self.save_insert_button.setObjectName("primary")
        self.save_insert_button.setEnabled(False)
        self.save_insert_button.clicked.connect(self.save_and_insert)
        footer.addWidget(self.save_insert_button)
        layout.addLayout(footer)
        if self.template_image is not None:
            self.instructions.setText("Testing a project image on a fresh phone screen. Optionally drag a search rectangle; no input is sent.")
            self.test_button.setEnabled(test_frame_provider is not None)
            self.result.setText(f"Template: {self.template_image.width()} × {self.template_image.height()} pixels. Test uses a new full-resolution capture.")

    @property
    def selected_region(self) -> Region | None:
        return self.canvas.selection

    def select_region(self, region: Region) -> None:
        self.canvas.set_selection(region)

    def _selection_changed(self, region: Region):
        converted = android_region(region, (self.frame.width(), self.frame.height()), self.source_size)
        self.coordinates.setText(f"Android: x={converted.x}, y={converted.y}, width={converted.width}, height={converted.height}"
                                 f" · crop: {region.width}×{region.height} encoded pixels")
        self.save_button.setEnabled(not self._busy)
        self.save_insert_button.setEnabled(not self._busy and self.save_directory is not None)
        self.test_button.setEnabled(not self._busy and (self.test_frame_provider is not None or self.match_source.currentIndex() == 0))

    def crop(self) -> QImage:
        region = self.selected_region
        if region is None:
            raise ValueError("Select a screenshot region first")
        return self.frame.copy(region.x, region.y, region.width, region.height)

    def _choose_save(self):
        default = str(self.save_directory / "target.png") if self.save_directory else "target.png"
        path, _ = QFileDialog.getSaveFileName(self, "Save captured region", default, "PNG (*.png)")
        if path:
            try:
                self.save_to(Path(path))
            except (OSError, ValueError) as error:
                self.result.setText(f"Could not save crop: {error}")

    def save_to(self, path: Path, *, emit_reference=True) -> None:
        """Save to a caller-approved path; native file dialog confirms overwrite."""
        image = self.crop()
        path = Path(path).resolve()
        output = QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        if not image.save(output, "PNG"):
            output.cancelWriting()
            raise OSError("PNG encoder could not save the selected region")
        if not output.commit():
            raise OSError(output.errorString())
        converted = android_region(self.selected_region, (self.frame.width(), self.frame.height()), self.source_size)
        self.asset_saved.emit(str(path), converted)
        if emit_reference:
            self.reference_ready.emit(reference_code(path, self.script_directory))
        self.result.setText(f"Saved {image.width()}×{image.height()} crop: {path}")

    def _command(self):
        name = self.filename.text().strip()
        if not name or name in (".", "..") or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Enter a PNG filename without a directory")
        if not name.lower().endswith(".png"):
            name += ".png"
        quoted = json.dumps(name, ensure_ascii=True)
        return (f"click({quoted})\n" if abs(self.threshold.value() - 0.85) < 0.0001 else
                f"click(Pattern({quoted}).similar({self.threshold.value():.2f}))\n")

    def _update_code_preview(self, *_):
        try:
            self.code_preview.setText(self._command().strip())
        except ValueError:
            self.code_preview.setText("Enter a target filename")

    def save_and_insert(self):
        try:
            command = self._command()
            name = self.filename.text().strip()
            if not name.lower().endswith(".png"):
                name += ".png"
            path = self.save_directory / name
            if path.exists() and QMessageBox.question(self, "Replace target?", f"Replace {name}?") != QMessageBox.StandardButton.Yes:
                return
            self.save_to(path, emit_reference=False)
        except (OSError, ValueError) as error:
            self.result.setText(f"Could not save crop: {error}")
            return
        self.command_ready.emit(command)
        self.accept()

    def start_match(self):
        if self._busy or self._closing:
            return
        if self.test_frame_provider is None and self.match_source.currentIndex() != 0:
            self.result.setText("Fresh-frame matching unavailable: selected-device capture is required.")
            return
        try:
            template = image_rgb(self.template_image if self.template_image is not None else self.crop())
            scales = validate_scales(tuple(float(value.strip()) for value in self.scales.text().split(",")))
            region = self.selected_region if self.search_selection.isChecked() else None
            if self.search_selection.isChecked() and region is None:
                raise ValueError("Draw a search rectangle first")
        except ValueError as error:
            self.result.setText(str(error))
            return
        threshold = self.threshold.value()
        preprocessing = self.preprocessing.currentText()
        provider = self.test_frame_provider if self.match_source.currentIndex() == 1 else lambda: self.frame.copy()
        expected_size = (self.frame.width(), self.frame.height())

        def operation():
            fresh = provider()
            if not isinstance(fresh, QImage) or fresh.isNull():
                raise ValueError("Selected device returned no decoded frame")
            if (fresh.width(), fresh.height()) != expected_size:
                raise ValueError("Device resolution or streaming quality changed; recapture the target before matching")
            matches = find_scaled(image_rgb(fresh), template, threshold, region,
                                  scales=scales, max_results=100, preprocess=preprocessing)
            return fresh.copy(), matches

        self._busy = True
        self._match_threshold = threshold
        self.canvas.setEnabled(False)
        self.comparison.matches = []
        self.comparison.update()
        self.tabs.setCurrentIndex(0)
        self.tabs.setTabEnabled(1, False)
        self.save_button.setEnabled(False)
        self.save_insert_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.threshold.setEnabled(False)
        self.scales.setEnabled(False)
        self.search_selection.setEnabled(False)
        self.result.setText(f"Capturing and matching {self.serial} off the UI thread…")
        self._job = _MatchJob(operation)
        self._job.signals.done.connect(self._match_done, Qt.ConnectionType.QueuedConnection)
        self.pool.start(self._job)

    @Slot(object, object)
    def _match_done(self, result, error):
        self._busy = False
        self._job = None
        if self._closing:
            super().reject()
            return
        self.canvas.setEnabled(True)
        self.threshold.setEnabled(True)
        self.scales.setEnabled(True)
        self.search_selection.setEnabled(True)
        self.save_button.setEnabled(self.selected_region is not None)
        self.save_insert_button.setEnabled(self.selected_region is not None and self.save_directory is not None)
        self.test_button.setEnabled((self.template_image is not None or self.selected_region is not None)
                                   and (self.test_frame_provider is not None or self.match_source.currentIndex() == 0))
        if error:
            self.canvas.matches = []
            self.result.setText(f"Match failed: {error}")
            self.canvas.update()
            self.match_finished.emit({"error": error, "matches": []})
            return
        fresh, matches = result
        # The comparison has its own image. The frozen capture remains exactly
        # what the user selected even when the live device has changed.
        self.comparison.image = fresh
        self.comparison.matches = matches
        self.comparison.update()
        self.tabs.setTabEnabled(1, True)
        self.tabs.setCurrentIndex(1)
        if not matches:
            self.result.setText(f"No match reached score {self._match_threshold:.2f} on the selected {self.serial} frame.")
        else:
            details = []
            for match in matches[:8]:
                region = android_region(match.region, (fresh.width(), fresh.height()), self.source_size)
                details.append(f"score {match.score:.3f}: ({region.x}, {region.y}, {region.width}, {region.height}), tap ({region.center.x}, {region.center.y})")
            prefix = "Ambiguous: multiple matches. " if len(matches) > 1 else "One match. "
            self.result.setText(prefix + " | ".join(details) + " · scores are not probabilities; no tap was sent.")
        self.match_finished.emit({"error": None, "matches": matches})

    def reject(self):
        if self._busy:
            self._closing = True
            self.result.setText("Waiting for the bounded device capture/match operation to finish…")
            return
        super().reject()

    def closeEvent(self, event):
        if self._busy:
            self._closing = True
            self.result.setText("Waiting for the bounded device capture/match operation to finish…")
            event.ignore()
        else:
            # QDialog's close handler emits rejected/finished. Merely accepting
            # the QWidget event would hide the dialog without releasing the
            # host's retained dialog reference.
            super().closeEvent(event)
