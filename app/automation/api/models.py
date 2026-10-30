"""Immutable image targets and full-resolution screen values for scripts."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import time
from uuid import uuid4

import numpy as np

from app.automation.api.errors import InvalidAsset, InvalidCoordinates
from app.vision.matching import Location, Region, validate_scales


def fraction(value: float, name: str = "similarity") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    try:
        valid = math.isfinite(value) and 0 <= value <= 1
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    return float(value)


@dataclass(frozen=True, slots=True)
class Offset:
    """Signed pixel displacement from an image match's center."""
    x: int = 0
    y: int = 0

    def __post_init__(self):
        if any(type(value) is not int or abs(value) > 100_000 for value in (self.x, self.y)):
            raise ValueError("Offsets must be integers between -100000 and 100000")


@dataclass(frozen=True, slots=True)
class Pattern:
    """Image-library reference with inclusive score threshold and search bounds.

    Builder methods return a new value. A score is normalized correlation, not
    a correctness probability. Use atScales() to request explicit resizing.
    """
    path: str
    similarity: float = 0.85
    region: Region | None = None
    target_offset: Offset = Offset()
    scales: tuple[float, ...] = (1.0,)

    def __post_init__(self):
        if not isinstance(self.path, str) or not self.path or "\x00" in self.path or len(self.path) > 4096:
            raise InvalidAsset("Pattern path must be a nonempty image reference of at most 4096 characters")
        object.__setattr__(self, "similarity", fraction(self.similarity))
        if self.region is not None and not isinstance(self.region, Region):
            raise ValueError("Pattern region must be a Region or None")
        if not isinstance(self.target_offset, Offset):
            raise ValueError("Pattern target_offset must be an Offset")
        object.__setattr__(self, "scales", validate_scales(self.scales))

    def similar(self, score: float) -> Pattern:
        """Return this pattern with an inclusive normalized score threshold."""
        return replace(self, similarity=fraction(score))

    def targetOffset(self, dx: int, dy: int) -> Pattern:
        """Return this pattern with a signed center-to-target pixel offset."""
        return replace(self, target_offset=Offset(dx, dy))

    def inRegion(self, region: Region) -> Pattern:
        """Return this pattern with search bounds in original Android pixels."""
        return replace(self, region=region)

    def atScales(self, *scales: float) -> Pattern:
        """Search explicit template scales (1–16 values, each 0.1–4); offsets stay screen pixels."""
        return replace(self, scales=validate_scales(scales))


@dataclass(frozen=True, slots=True)
class Match:
    """A match tied to one serial, source geometry and captured frame."""
    region: Region
    score: float
    device_serial: str
    source_size: tuple[int, int]
    frame_id: str
    template: str
    target_offset: Offset = Offset()

    def __post_init__(self):
        if not isinstance(self.region, Region) or not isinstance(self.target_offset, Offset):
            raise ValueError("Match requires a Region and Offset")
        object.__setattr__(self, "score", fraction(self.score, "score"))
        if not isinstance(self.device_serial, str) or not self.device_serial:
            raise ValueError("Match requires its device serial")
        if (not isinstance(self.source_size, tuple) or len(self.source_size) != 2
                or any(type(value) is not int or value <= 0 for value in self.source_size)):
            raise ValueError("Match requires original screen dimensions")
        if self.region.x + self.region.width > self.source_size[0] or self.region.y + self.region.height > self.source_size[1]:
            raise InvalidCoordinates("Match lies outside its captured screen")
        if not isinstance(self.frame_id, str) or not self.frame_id or not isinstance(self.template, str) or not self.template:
            raise ValueError("Match requires its captured frame ID and template reference")

    @property
    def target(self) -> Location:
        """Center plus explicit offset, rejecting a target outside its screen."""
        x = self.region.center.x + self.target_offset.x
        y = self.region.center.y + self.target_offset.y
        if not (0 <= x < self.source_size[0] and 0 <= y < self.source_size[1]):
            raise InvalidCoordinates("Image target offset lies outside the screen")
        return Location(x, y)


@dataclass(frozen=True, slots=True)
class Screen:
    """Owned immutable packed RGB screenshot, separate from preview overlays."""
    serial: str
    rgb: bytes
    width: int
    height: int
    frame_id: str
    captured_at: float

    def __post_init__(self):
        if not isinstance(self.serial, str) or not self.serial:
            raise ValueError("Screen requires its device serial")
        if any(type(value) is not int or not 0 < value <= 16_384 for value in (self.width, self.height)):
            raise ValueError("Screen dimensions are unsupported")
        if self.width * self.height > 100_000_000:
            raise ValueError("Screen exceeds pixel limit")
        if not isinstance(self.rgb, bytes) or len(self.rgb) != self.width * self.height * 3:
            raise ValueError("Screen requires exact immutable RGB bytes")
        if not isinstance(self.frame_id, str) or not self.frame_id:
            raise ValueError("Screen requires its captured frame ID")
        valid_timestamp = not isinstance(self.captured_at, bool) and isinstance(self.captured_at, (int, float))
        if valid_timestamp:
            try:
                valid_timestamp = math.isfinite(self.captured_at) and self.captured_at >= 0
            except OverflowError:
                valid_timestamp = False
        if not valid_timestamp:
            raise ValueError("Screen requires a finite nonnegative monotonic timestamp")

    @classmethod
    def from_array(cls, serial: str, image: np.ndarray) -> Screen:
        if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
                or image.ndim != 3 or image.shape[2] != 3):
            raise ValueError("Capture must be an RGB uint8 array")
        height, width = image.shape[:2]
        if (not 0 < width <= 16_384 or not 0 < height <= 16_384
                or width * height > 100_000_000):
            raise ValueError("Capture dimensions are unsupported")
        return cls(serial, image.tobytes(), width, height, uuid4().hex, time.monotonic())

    @property
    def resolution(self) -> tuple[int, int]:
        return self.width, self.height

    def to_numpy(self) -> np.ndarray:
        """Return a read-only RGB view; use .copy() for editable pixels."""
        return np.frombuffer(self.rgb, dtype=np.uint8).reshape(self.height, self.width, 3)
