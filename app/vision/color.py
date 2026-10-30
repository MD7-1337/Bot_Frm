"""Exact/tolerant RGB pixel operations in original screenshot coordinates."""
import numpy as np

from app.vision.matching import Location, Region, _image


def pixel(frame, x, y):
    _image("frame", frame)
    if type(x) is not int or type(y) is not int or not 0 <= x < frame.shape[1] or not 0 <= y < frame.shape[0]:
        raise ValueError("Pixel coordinates lie outside the screenshot")
    return tuple(int(channel) for channel in frame[y, x])


def find_color(frame, color, tolerance=0, region=None, limit=100):
    """Return at most limit pixel locations in row-major order; no region clustering."""
    _image("frame", frame)
    if not isinstance(color, (tuple, list)) or len(color) != 3 or any(type(value) is not int or not 0 <= value <= 255 for value in color):
        raise ValueError("Color must be three integer RGB channels from 0 to 255")
    if type(tolerance) is not int or not 0 <= tolerance <= 255:
        raise ValueError("Tolerance must be an integer from 0 to 255 for every channel")
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("Limit must be an integer from 1 to 10000")
    height, width = frame.shape[:2]
    search = Region(0, 0, width, height) if region is None else region
    if not isinstance(search, Region) or search.x + search.width > width or search.y + search.height > height:
        raise ValueError("Color search region lies outside the screenshot")
    # Process one row at a time to avoid allocating full-frame masks/coordinate
    # arrays for a uniform screenshot or a very broad tolerance.
    output = []
    target = np.asarray(color, dtype=np.int16)
    for y in range(search.y, search.y + search.height):
        row = frame[y, search.x:search.x + search.width].astype(np.int16)
        xs = np.flatnonzero(np.all(np.abs(row - target) <= tolerance, axis=1))
        for x in xs[:limit - len(output)]:
            output.append(Location(search.x + int(x), y))
        if len(output) == limit:
            break
    return output
