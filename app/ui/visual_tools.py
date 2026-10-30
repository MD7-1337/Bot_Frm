"""Project image library and real Pattern code generation for Monaco."""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (QDoubleSpinBox, QFormLayout, QGridLayout, QLabel,
                              QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget)

from app.projects.library import AssetLibrary, IMAGE_EXTENSIONS
from app.vision.matching import Region, validate_scales


def scan_assets(root: Path) -> tuple[list[str], bool]:
    """Bounded scan; never follow directory symlinks or include escaped files."""
    library = AssetLibrary(root)
    references = []
    scanned = 0
    if not library.image_root.is_dir():
        return [], False
    for index, (directory, folders, files) in enumerate(os.walk(library.image_root, followlinks=False)):
        if index >= 2000:
            return sorted(references), True
        folders[:] = sorted(folder for folder in folders if not (Path(directory) / folder).is_symlink())
        for filename in sorted(files):
            scanned += 1
            if scanned > 5000 or len(references) >= 500:
                return sorted(references), True
            candidate = Path(directory) / filename
            if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                canonical = library.resolve(candidate)
                references.append(canonical.relative_to(library.project_root).as_posix())
            except (OSError, ValueError):
                continue
    return sorted(set(references)), False


def load_asset(root: Path, reference: str):
    """Decode a contained, bounded raster image off the GUI thread."""
    path = AssetLibrary(root).resolve(reference)
    reader = QImageReader(str(path))
    if bytes(reader.format()).lower() not in {b"png", b"jpeg", b"bmp", b"webp"}:
        raise ValueError("Asset is not a supported raster image")
    size = reader.size()
    if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > 16_777_216:
        raise ValueError("Asset dimensions exceed the 16 megapixel limit")
    image = reader.read()
    if image.isNull():
        raise ValueError("Asset image could not be decoded")
    return image


class VisualToolsPanel(QWidget):
    refresh_requested = Signal()
    capture_requested = Signal()
    save_requested = Signal()
    project_requested = Signal()
    asset_selected = Signal(str)
    insert_requested = Signal(str)
    test_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        hint = QLabel("Select a phone in Device Manager, capture a region, then select an image below to insert or test it.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QGridLayout()
        for index, (label, signal) in enumerate((("Capture region…", self.capture_requested),
                                                ("Save full screenshot…", self.save_requested),
                                                ("Choose project…", self.project_requested),
                                                ("Refresh image library", self.refresh_requested))):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, target=signal: target.emit())
            buttons.addWidget(button, index // 2, index % 2)
        layout.addLayout(buttons)
        self.assets = QListWidget()
        self.assets.setAccessibleName("Project image library")
        self.assets.currentTextChanged.connect(self.asset_selected)
        layout.addWidget(self.assets, stretch=1)
        self.thumbnail = QLabel("Select an image to preview")
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setMinimumHeight(80)
        self.thumbnail.setMaximumHeight(140)
        layout.addWidget(self.thumbnail)
        options = QFormLayout()
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 1)
        self.threshold.setDecimals(2)
        self.threshold.setValue(.9)
        self.threshold.setSingleStep(.01)
        self.scales = QLineEdit("1.0")
        self.scales.setToolTip("Explicit template scales, e.g. 0.75, 1, 1.25. At most 16 values between 0.1 and 4.")
        self.offset = QLineEdit("0, 0")
        self.region = QLineEdit()
        self.region.setPlaceholderText("optional x, y, width, height")
        for label, widget in (("Minimum score", self.threshold), ("Template scales", self.scales),
                              ("Target offset dx, dy", self.offset), ("Search region", self.region)):
            widget.setMaxLength(256) if isinstance(widget, QLineEdit) else None
            options.addRow(label, widget)
        layout.addLayout(options)
        insert = QGridLayout()
        for index, (label, command) in enumerate((("Insert click", "click"), ("Insert find", "find"),
                                                  ("Insert wait", "waitImage"), ("Insert image path", "path"))):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, target=command: self.insert_requested.emit(target))
            insert.addWidget(button, index // 2, index % 2)
        layout.addLayout(insert)
        self.test_button = QPushButton("Test selected image on fresh phone screen")
        self.test_button.clicked.connect(lambda: self.test_requested.emit())
        layout.addWidget(self.test_button)
        self.status = QLabel("Image library has not been scanned yet.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def selected_reference(self):
        item = self.assets.currentItem()
        if item is None:
            raise ValueError("Select an image in Screenshot & Visual Tools first")
        return item.text()

    def set_entries(self, entries, truncated=False):
        selected = self.assets.currentItem().text() if self.assets.currentItem() else None
        self.assets.clear()
        self.assets.addItems(entries)
        self.status.setText(f"{len(entries)} project image(s)." + (" Scan limit reached; showing the first 500 images / 5000 files." if truncated else ""))
        if selected in entries:
            self.assets.setCurrentRow(entries.index(selected))

    def set_thumbnail(self, image):
        self.thumbnail.setPixmap(QPixmap.fromImage(image).scaled(240, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation))
        self.thumbnail.setToolTip(f"Original template: {image.width()} × {image.height()} pixels")

    def options(self):
        scales = validate_scales(tuple(float(part.strip()) for part in self.scales.text().split(",")))
        offset = tuple(int(part.strip()) for part in self.offset.text().split(","))
        if len(offset) != 2 or any(abs(value) > 100_000 for value in offset):
            raise ValueError("Target offset requires dx, dy between -100000 and 100000")
        region = Region(*(int(part.strip()) for part in self.region.text().split(","))) if self.region.text().strip() else None
        return self.threshold.value(), scales, offset, region

    def code(self, command):
        reference = json.dumps(self.selected_reference(), ensure_ascii=False)
        if command == "path":
            return reference + "\n"
        threshold, scales, offset, region = self.options()
        pattern = f"Pattern({reference}).similar({threshold})"
        if scales != (1.0,):
            pattern += f".atScales({', '.join(map(str, scales))})"
        if offset != (0, 0):
            pattern += f".targetOffset({offset[0]}, {offset[1]})"
        if region:
            pattern += f".inRegion(Region({region.x}, {region.y}, {region.width}, {region.height}))"
        if command not in {"click", "find", "waitImage"}:
            raise ValueError("Unsupported visual insertion command")
        return f"{command}({pattern}" + (", timeout=10)\n" if command == "waitImage" else ")\n")
