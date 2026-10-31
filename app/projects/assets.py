"""Coordinate and Python-reference contracts for captured image assets."""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.vision.matching import Region


def _size(value: tuple[int, int], name: str) -> tuple[int, int]:
    if (not isinstance(value, tuple) or len(value) != 2
            or any(type(item) is not int or item <= 0 for item in value)):
        raise ValueError(f"{name} must contain two positive integer dimensions")
    return value


def android_region(region: Region, image_size: tuple[int, int], source_size: tuple[int, int]) -> Region:
    """Map half-open encoded-image bounds to enclosing Android pixel bounds.

    The frame and source dimensions refer to the same current orientation.
    Rounded-outward edges retain every selected source pixel at reduced quality.
    This mapping does not pretend a downscaled crop has full-resolution detail.
    """
    image_width, image_height = _size(image_size, "image_size")
    source_width, source_height = _size(source_size, "source_size")
    if not isinstance(region, Region):
        raise ValueError("selection must be a Region")
    if region.x + region.width > image_width or region.y + region.height > image_height:
        raise ValueError("selection lies outside the captured image")
    left = region.x * source_width // image_width
    top = region.y * source_height // image_height
    right = ((region.x + region.width) * source_width + image_width - 1) // image_width
    bottom = ((region.y + region.height) * source_height + image_height - 1) // image_height
    return Region(left, top, min(right, source_width) - left, min(bottom, source_height) - top)


def reference_code(path: Path, script_directory: Path | None = None) -> str:
    """Return inert ordinary Python assigning a safely quoted asset path.

    An explicit script directory permits a portable relative reference. The
    caller controls the selected save path; this never imports or executes it.
    """
    path = Path(path).resolve()
    reference = str(path)
    if script_directory is not None:
        try:
            reference = os.path.relpath(path, Path(script_directory).resolve())
        except ValueError:  # Different Windows drives cannot form a relative path.
            pass
        else:
            reference = reference.replace(os.sep, "/")
    return "image_path = " + json.dumps(reference, ensure_ascii=True) + "\n"
