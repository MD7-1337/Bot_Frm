"""Deterministic, region-aware OpenCV template-matching proof of concept.

Inputs are uint8 RGB arrays. The caller owns the screenshot pixels; this module
never annotates or changes them. Scores use TM_CCOEFF_NORMED and are similarity
scores, not probabilities. Constant-colour templates have no distinguishing
spatial information and are rejected explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np
from numpy.typing import NDArray

RGBImage = NDArray[np.uint8]


class ImageNotFound(LookupError):
    """No match met the requested similarity threshold."""


def _integer(name: str, value: int, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True, slots=True)
class Location:
    x: int
    y: int

    def __post_init__(self) -> None:
        _integer("x", self.x)
        _integer("y", self.y)


@dataclass(frozen=True, slots=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        _integer("x", self.x)
        _integer("y", self.y)
        _integer("width", self.width, 1)
        _integer("height", self.height, 1)

    @property
    def center(self) -> Location:
        return Location(self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True, slots=True)
class Match:
    region: Region
    score: float

    @property
    def target(self) -> Location:
        """Centre in full screenshot coordinates, with no preview transform."""
        return self.region.center


def _image(name: str, image: RGBImage) -> None:
    if not isinstance(image, np.ndarray):
        raise ValueError(f"{name} must be a numpy uint8 RGB array")
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"{name} must have dtype uint8 and shape (height, width, 3)")
    if image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError(f"{name} must not be empty")


def _fraction(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    return result


def _settings(frame, template, threshold, region, max_results, nms_iou):
    _image("frame", frame)
    _image("template", template)
    threshold = _fraction("threshold", threshold)
    nms_iou = _fraction("nms_iou", nms_iou)
    if nms_iou == 1:
        raise ValueError("nms_iou must be less than 1")
    _integer("max_results", max_results, 1)
    if max_results > 10_000:
        raise ValueError("max_results must not exceed 10000")
    if float(np.var(template.astype(np.float32), axis=(0, 1)).sum()) <= 1e-8:
        raise ValueError("constant templates cannot be matched with TM_CCOEFF_NORMED")

    frame_height, frame_width = frame.shape[:2]
    if region is None:
        region = Region(0, 0, frame_width, frame_height)
    if not isinstance(region, Region):
        raise ValueError("region must be a Region or None")
    if region.x + region.width > frame_width or region.y + region.height > frame_height:
        raise ValueError("search region lies outside the frame")
    return threshold, region, nms_iou


def find_all(
    frame: RGBImage,
    template: RGBImage,
    threshold: float = 0.9,
    region: Region | None = None,
    *,
    max_results: int = 100,
    nms_iou: float = 0.3,
) -> list[Match]:
    """Return score-descending matches, suppressing overlapping rectangles.

    ``region`` must lie wholly within ``frame``; returned coordinates always use
    the full frame. A template larger than the selected search area returns an
    empty list. ``max_results`` bounds the result set and suppression iterations.
    Inputs with invalid shape/type, constant templates, out-of-bounds regions or
    nonfinite settings raise ``ValueError``. This is a single-scale matcher;
    explicit multi-scale searches are available through find_scaled().
    """
    threshold, region, nms_iou = _settings(frame, template, threshold, region, max_results, nms_iou)
    height, width = template.shape[:2]
    if height > region.height or width > region.width:
        return []

    search = frame[region.y:region.y + region.height, region.x:region.x + region.width]
    response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    response = np.nan_to_num(response, nan=-1.0, posinf=-1.0, neginf=-1.0)
    # Floating point error can put a normalized score marginally outside [-1, 1].
    np.clip(response, -1.0, 1.0, out=response)
    matches: list[Match] = []
    for _ in range(max_results):
        _, score, _, (x, y) = cv2.minMaxLoc(response)
        if score < threshold:
            break
        matches.append(Match(Region(region.x + x, region.y + y, width, height), score))

        # Only nearby candidates can overlap. Suppress by exact intersection over
        # union, keeping separate adjacent targets even in a crowded screenshot.
        left, right = max(0, x - width + 1), min(response.shape[1], x + width)
        top, bottom = max(0, y - height + 1), min(response.shape[0], y + height)
        xs = np.arange(left, right)
        ys = np.arange(top, bottom)
        intersection_width = np.maximum(0, width - np.abs(xs - x))
        intersection_height = np.maximum(0, height - np.abs(ys - y))
        intersection = intersection_height[:, None] * intersection_width[None, :]
        iou = intersection / (2 * width * height - intersection)
        subresponse = response[top:bottom, left:right]
        subresponse[iou > nms_iou] = -1.0
    return matches


def find(
    frame: RGBImage,
    template: RGBImage,
    threshold: float = 0.9,
    region: Region | None = None,
) -> Match:
    """Return the best match, or raise ImageNotFound; other errors are ValueError."""
    matches = find_all(frame, template, threshold, region, max_results=1)
    if not matches:
        raise ImageNotFound(f"No image match reached similarity score {threshold}")
    return matches[0]


def validate_scales(scales) -> tuple[float, ...]:
    """Explicit finite scale set; bounded to 16 requests in [0.1, 4]."""
    if not isinstance(scales, (tuple, list)) or not 1 <= len(scales) <= 16:
        raise ValueError("scales must contain between 1 and 16 numbers")
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not .1 <= value <= 4 or not math.isfinite(value) for value in scales):
        raise ValueError("scales must be finite numbers between 0.1 and 4")
    return tuple(dict.fromkeys(float(value) for value in scales))


def find_scaled(frame: RGBImage, template: RGBImage, threshold: float = .9,
                region: Region | None = None, *, scales=(1.0,), max_results=100,
                nms_iou=.3) -> list[Match]:
    """Explicit multi-scale correlation with full-frame coordinates and cross-scale NMS.

    Offsets remain original-screen pixels. This does not normalize DPI, lighting,
    perspective or animation. Each scale is searched independently; at most
    max_results candidates per scale enter deterministic global suppression.
    """
    scales = validate_scales(scales)
    # Preserve the exact existing default path; other requests search only
    # their specified dimensions rather than computing implicit scale-one results.
    if scales == (1.0,):
        return find_all(frame, template, threshold, region, max_results=max_results, nms_iou=nms_iou)
    threshold, region, nms_iou = _settings(frame, template, threshold, region, max_results, nms_iou)
    candidates = []
    height, width = template.shape[:2]
    search_width, search_height = region.width, region.height
    dimensions = set()
    for scale in scales:
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        if size in dimensions or size[0] > search_width or size[1] > search_height:
            continue
        dimensions.add(size)
        # Prevent unexpectedly huge allocations even for a caller's giant template.
        if size[0] * size[1] > 16_777_216:
            raise ValueError("Scaled template exceeds 16 megapixels")
        resized = template if size == (width, height) else cv2.resize(
            template, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        # Downsampling can legitimately eliminate all spatial information.
        if float(np.var(resized.astype(np.float32), axis=(0, 1)).sum()) <= 1e-8:
            continue
        candidates.extend(find_all(frame, resized, threshold, region,
                                   max_results=max_results, nms_iou=nms_iou))
    candidates.sort(key=lambda m: (-m.score, m.region.y, m.region.x, m.region.width, m.region.height))
    output = []
    for match in candidates:
        a = match.region
        overlaps = False
        for kept in output:
            b = kept.region
            intersection = max(0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x)) * max(0, min(a.y + a.height, b.y + b.height) - max(a.y, b.y))
            if intersection / (a.width * a.height + b.width * b.height - intersection) > nms_iou:
                overlaps = True
                break
        if not overlaps:
            output.append(match)
            if len(output) == max_results:
                break
    return output
