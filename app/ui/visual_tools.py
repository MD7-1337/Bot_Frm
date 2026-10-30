"""Project image library and real Pattern code generation for Monaco."""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (QDoubleSpinBox, QFormLayout, QGridLayout, QLabel,
                              QHBoxLayout, QLineEdit, QListWidget, QPushButton, QSplitter, QVBoxLayout, QWidget)
from app.ui.components import button, label, scroll, surface

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Capture your first image target, or select a saved target from this project's image library.", "notice"))
        split = QSplitter()
        library, listing = surface()
        listing.addWidget(label("IMAGE LIBRARY", "eyebrow"))
        controls = QHBoxLayout()
        controls.addWidget(button("Choose project…", self.project_requested.emit))
        controls.addWidget(button("Refresh image library", self.refresh_requested.emit))
        listing.addLayout(controls)
        self.assets = QListWidget()
        self.assets.setAccessibleName("Project image library")
        self.assets.currentTextChanged.connect(self.asset_selected)
        listing.addWidget(self.assets, stretch=1)
        self.capture_button = button("Capture region…", self.capture_requested.emit, primary=True)
        self.save_button = button("Save full screenshot…", self.save_requested.emit)
        listing.addWidget(self.capture_button)
        listing.addWidget(self.save_button)
        split.addWidget(library)
        properties, form_layout = surface()
        form_layout.addWidget(label("TARGET INSPECTOR", "eyebrow"))
        self.thumbnail = label("Select a target to inspect its pixels")
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setMinimumHeight(140)
        self.thumbnail.setMaximumHeight(240)
        form_layout.addWidget(self.thumbnail)
        options = QFormLayout()
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 1)
        self.threshold.setDecimals(2)
        self.threshold.setValue(.9)
        self.threshold.setSingleStep(.01)
        self.threshold.setToolTip("Normalized matching score, not a probability of correctness")
        self.scales = QLineEdit("1.0")
        self.scales.setToolTip("Explicit scales: 0.75, 1, 1.25. At most 16 values between 0.1 and 4.")
        self.offset = QLineEdit("0, 0")
        self.region = QLineEdit()
        self.region.setPlaceholderText("optional x, y, width, height")
        for text, widget in (("Minimum score", self.threshold), ("Template scales", self.scales),
                             ("Target offset", self.offset), ("Search bounds", self.region)):
            if isinstance(widget, QLineEdit):
                widget.setMaxLength(256)
            options.addRow(text, widget)
        form_layout.addLayout(options)
        insert = QGridLayout()
        self.insert_buttons = []
        for index, (text, command) in enumerate((("Insert click", "click"), ("Insert find", "find"),
                                                ("Insert wait", "waitImage"), ("Insert image path", "path"))):
            widget = button(text, lambda target=command: self.insert_requested.emit(target))
            insert.addWidget(widget, index // 2, index % 2)
            self.insert_buttons.append(widget)
        form_layout.addLayout(insert)
        self.test_button = button("Test on fresh phone screen", self.test_requested.emit, primary=True)
        form_layout.addWidget(self.test_button)
        form_layout.addWidget(label("Matching never sends input. Review scores, ambiguity and original Android coordinates before inserting a click."))
        form_layout.addStretch()
        split.addWidget(scroll(properties))
        split.setSizes([320, 440])
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, stretch=1)
        self.status = label("Choose a project, then capture or select a target.")
        layout.addWidget(self.status)

    def set_control_state(self, available, editor_ready):
        selected = self.assets.currentItem() is not None
        self.capture_button.setEnabled(available)
        self.save_button.setEnabled(available)
        self.test_button.setEnabled(available and selected)
        for widget in self.insert_buttons:
            widget.setEnabled(selected and editor_ready)
        self.test_button.setToolTip("Match this template on a new screenshot" if available and selected else "Select both a connected phone and an image")

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
        self.thumbnail.setPixmap(QPixmap.fromImage(image).scaled(360, 200, Qt.AspectRatioMode.KeepAspectRatio,
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
