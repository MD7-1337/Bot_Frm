"""Geometry unit checks plus an opt-in actual Qt rendering/input probe."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.ui.preview import PreviewViewport


@pytest.mark.parametrize("encoded,source,widget", [
    ((100, 200), (1000, 2000), (500, 500)),
    ((360, 800), (1080, 2400), (981, 643)),
    ((368, 800), (1080, 2340), (981, 643)),
    ((800, 368), (2340, 1080), (643, 981)),
])
def test_scaled_video_maps_original_device_pixel_centers(encoded, source, widget):
    viewport = PreviewViewport(*encoded, *widget, *source)
    assert viewport.input_available
    for x, y in ((0, 0), (source[0] - 1, source[1] - 1),
                 (source[0] // 2, source[1] // 2), (source[0] // 3, source[1] // 4)):
        assert viewport.to_device(*viewport.from_device(x, y)) == (x, y)
    left, top, width, height = viewport.content_rect
    assert viewport.to_device(left - 0.01, top + height / 2) is None
    assert viewport.to_device(left + width, top + height / 2) is None
    assert viewport.to_device(left + width / 2, top - 0.01) is None
    assert viewport.to_device(left + width / 2, top + height) is None


def test_unknown_and_obsolete_orientation_disable_input_but_keep_render_rectangle():
    unknown = PreviewViewport(100, 200, 500, 500, None, None)
    mismatch = PreviewViewport(100, 200, 500, 500, 2000, 1000)
    for viewport in (unknown, mismatch):
        assert not viewport.input_available
        assert viewport.to_device(250, 250) is None
        assert viewport.content_rect == (125, 0, 250, 500)
        with pytest.raises(ValueError):
            viewport.from_device(1, 1)


@pytest.mark.parametrize("point", [(float("nan"), 1), (1, float("inf")), (-1, 5)])
def test_invalid_pointer_rejected(point):
    viewport = PreviewViewport(100, 200, 500, 500, 1000, 2000)
    assert viewport.to_device(*point) is None


@pytest.mark.parametrize("arguments", [
    (0, 200, 500, 500, 1000, 2000),
    (100, 200, 0, 500, 1000, 2000),
    (100, 200, 500, 500, None, 2000),
    (100, 200, 500, 500, True, 2000),
])
def test_invalid_frame_geometry_rejected(arguments):
    with pytest.raises(ValueError):
        PreviewViewport(*arguments)


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Enable actual Qt GUI probes explicitly")
def test_actual_rgb_preview_and_mouse_gestures(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path), STUDIO_CONFIG_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, str(root / "tests/probe_preview_live.py")],
                            cwd=root, env=environment, capture_output=True,
                            text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
    for key in ("rgb", "scaled_coordinates", "single_double_tap", "long_swipe", "invalidation", "overlays"):
        assert f'"{key}": true' in result.stdout
