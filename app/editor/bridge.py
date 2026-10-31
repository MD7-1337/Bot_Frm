"""Narrow editor bridge: source text and diagnostics only, never script execution."""
from __future__ import annotations

import ast
import base64
from collections import OrderedDict
import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QImageReader

from app.editor.catalog import api_catalog
from app.projects.library import AssetLibrary

MAX_SOURCE = 1_000_000
MAX_REFERENCES = 128
MAX_IMAGE_PIXELS = 16_777_216
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _column(source_line: str, utf8_offset: int) -> int:
    """Convert CPython AST byte columns into Monaco's UTF-16 columns."""
    prefix = source_line.encode("utf-8")[:utf8_offset].decode("utf-8", errors="ignore")
    return len(prefix.encode("utf-16-le")) // 2 + 1


def image_references(source: str) -> list[dict]:
    """Find image string literals through Python syntax, without executing it."""
    if not isinstance(source, str) or len(source) > MAX_SOURCE:
        return []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    lines = source.splitlines()
    references = []
    for index, node in enumerate(ast.walk(tree)):
        if index >= 30_000 or len(references) >= MAX_REFERENCES:
            break
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if not 0 < len(value) <= 2048 or Path(value).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if not node.end_lineno or node.end_col_offset is None:
            continue
        references.append({"reference": value, "start_line": node.lineno,
                           "start_column": _column(lines[node.lineno - 1], node.col_offset),
                           "end_line": node.end_lineno,
                           "end_column": _column(lines[node.end_lineno - 1], node.end_col_offset)})
    return references


def source_diagnostics(source: str) -> list[dict]:
    if len(source) > MAX_SOURCE:
        return [{"line": 1, "column": 1, "message": "Document exceeds 1 MB character limit"}]
    try:
        ast.parse(source)
    except (SyntaxError, ValueError) as error:
        return [{"line": getattr(error, "lineno", None) or 1,
                 "column": getattr(error, "offset", None) or 1,
                 "message": str(getattr(error, "msg", error))}]
    except (RecursionError, MemoryError):
        return [{"line": 1, "column": 1, "message": "Source too complex to analyze"}]
    return []


class EditorBridge(QObject):
    ready = Signal()
    changed = Signal(str)
    failed = Signal(str)
    breakpoints_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._assets: AssetLibrary | None = None
        self._thumbnail_cache: OrderedDict[tuple, dict] = OrderedDict()

    def set_project_root(self, root: Path | str | None, script_dir: Path | str | None = None):
        """Host-only configuration. This method is deliberately not a Qt slot."""
        self._assets = None if root is None else AssetLibrary(root, script_dir=script_dir)
        self._thumbnail_cache.clear()

    @Slot()
    def editorReady(self) -> None:
        self.ready.emit()

    @Slot(str)
    def documentChanged(self, source: str) -> None:
        if len(source) <= MAX_SOURCE:
            self.changed.emit(source)
        else:
            self.failed.emit("Document exceeds editor size limit")

    @Slot(str)
    def breakpointsChanged(self, raw: str) -> None:
        # Source metadata only: this slot cannot start or control any execution.
        if len(raw) > 12_000:
            return
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return
        key = None
        if isinstance(payload, dict):
            key = payload.get("key")
            if not isinstance(key, str) or len(key) > 4096:
                return
            lines = payload.get("lines")
        else:
            lines = payload
        if not isinstance(lines, list) or len(lines) > 1000 or any(type(line) is not int or not 1 <= line <= 1_000_000 for line in lines):
            return
        self.breakpoints_changed.emit({"key": key, "lines": sorted(set(lines))} if key is not None else sorted(set(lines)))

    @Slot(str, result=str)
    def diagnostics(self, source: str) -> str:
        return json.dumps(source_diagnostics(source))

    @Slot(result=str)
    def apiCatalog(self) -> str:
        return json.dumps(api_catalog())

    def _resolve_image(self, reference):
        if self._assets is None:
            raise ValueError("Select a project to resolve image references")
        if not isinstance(reference, str) or not 0 < len(reference) <= 2048:
            raise ValueError("Invalid image reference")
        return self._assets.resolve(reference)

    @Slot(str, result=str)
    def imageReferences(self, source: str) -> str:
        references = image_references(source)
        for item in references:
            try:
                self._resolve_image(item["reference"])
                item.update(available=True, message="Image in current project")
            except FileNotFoundError:
                item.update(available=False, message="Image not found in current project")
            except (ValueError, OSError):
                item.update(available=False, message="Image unavailable or outside the current project")
        return json.dumps(references)

    @Slot(str, result=str)
    def imagePreview(self, reference: str) -> str:
        """Return a bounded PNG thumbnail; never expose arbitrary file bytes."""
        try:
            path = self._resolve_image(reference)
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            cached = self._thumbnail_cache.get(key)
            if cached is not None:
                self._thumbnail_cache.move_to_end(key)
                return json.dumps({**cached, "reference": reference})
            reader = QImageReader(str(path))
            # Filename containment alone is insufficient for decoder plugins:
            # e.g. an SVG disguised as .png can contain external references.
            # This read-only bridge accepts only self-contained raster formats.
            if bytes(reader.format()).lower() not in (b"png", b"jpg", b"jpeg", b"bmp", b"webp"):
                raise ValueError("Unsupported thumbnail image format")
            size = reader.size()
            width, height = size.width(), size.height()
            if not 0 < width <= 16_384 or not 0 < height <= 16_384 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions exceed preview limits or cannot be decoded")
            factor = min(1.0, 256 / width, 256 / height)
            reader.setScaledSize(QSize(max(1, round(width * factor)), max(1, round(height * factor))))
            image = reader.read()
            if image.isNull():
                raise ValueError("Image could not be decoded")
            # Plugins that ignore scaled decoding still receive bounded output.
            if image.width() > 256 or image.height() > 256:
                image = image.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio)
            data = QByteArray()
            buffer = QBuffer(data)
            if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, "PNG"):
                raise ValueError("Image thumbnail could not be encoded")
            if len(data) > 300_000:
                raise ValueError("Image thumbnail exceeds preview limit")
            result = {"available": True, "reference": reference, "width": width, "height": height,
                      "data_url": "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")}
            self._thumbnail_cache[key] = result
            while len(self._thumbnail_cache) > 32:
                self._thumbnail_cache.popitem(last=False)
        except FileNotFoundError:
            result = {"available": False, "reference": reference, "error": "Image not found in current project"}
        except (ValueError, OSError):
            result = {"available": False, "reference": reference, "error": "Image unavailable, invalid or outside the current project"}
        return json.dumps(result)

    @Slot(str)
    def reportError(self, message: str) -> None:
        self.failed.emit(message[:2000])
