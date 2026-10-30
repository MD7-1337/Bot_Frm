"""Coordinate transforms for fitted, letterboxed, clockwise-rotated previews."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Viewport:
    source_width: int
    source_height: int
    viewport_width: int
    viewport_height: int
    rotation: int = 0

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in (self.source_width, self.source_height, self.viewport_width, self.viewport_height)):
            raise ValueError("Source and viewport dimensions must be positive integers.")
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("Rotation must be 0, 90, 180, or 270 clockwise degrees.")

    @property
    def _rotated_size(self) -> tuple[int, int]:
        if self.rotation in (90, 270):
            return self.source_height, self.source_width
        return self.source_width, self.source_height

    @property
    def scale(self) -> float:
        width, height = self._rotated_size
        return min(self.viewport_width / width, self.viewport_height / height)

    @property
    def content_rect(self) -> tuple[float, float, float, float]:
        width, height = self._rotated_size
        scaled_width, scaled_height = width * self.scale, height * self.scale
        return ((self.viewport_width - scaled_width) / 2, (self.viewport_height - scaled_height) / 2, scaled_width, scaled_height)

    def to_device(self, x: float, y: float) -> tuple[int, int] | None:
        """Return a source pixel, or None when the event is in a letterbox."""
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        left, top, width, height = self.content_rect
        if not (left <= x < left + width and top <= y < top + height):
            return None
        # Pointer positions cover pixel areas; inverse rotation uses discrete
        # pixel indexes so the last pixel never becomes width/height itself.
        rx, ry = int((x - left) / self.scale), int((y - top) / self.scale)
        if self.rotation == 90:
            return ry, self.source_height - 1 - rx
        if self.rotation == 180:
            return self.source_width - 1 - rx, self.source_height - 1 - ry
        if self.rotation == 270:
            return self.source_width - 1 - ry, rx
        return rx, ry

    def from_device(self, x: int, y: int) -> tuple[float, float]:
        """Map a source pixel center into the fitted preview."""
        if type(x) is not int or type(y) is not int or not (0 <= x < self.source_width and 0 <= y < self.source_height):
            raise ValueError("Source coordinates are outside the captured screen.")
        if self.rotation == 90:
            rx, ry = self.source_height - 1 - y, x
        elif self.rotation == 180:
            rx, ry = self.source_width - 1 - x, self.source_height - 1 - y
        elif self.rotation == 270:
            rx, ry = y, self.source_width - 1 - x
        else:
            rx, ry = x, y
        left, top, _, _ = self.content_rect
        return left + (rx + 0.5) * self.scale, top + (ry + 0.5) * self.scale
