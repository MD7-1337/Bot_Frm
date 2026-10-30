"""Actual OpenCV scales, ownership and API compatibility on known pixels."""
from dataclasses import FrozenInstanceError

import cv2
import numpy as np
import pytest

from app.automation.api import Device, Location, Pattern, Region
from app.projects.library import AssetLibrary
from app.vision.matching import find_all, find_scaled, validate_scales


@pytest.fixture
def scene():
    rng = np.random.default_rng(567)
    template = rng.integers(0, 255, (16, 20, 3), np.uint8)
    frame = rng.integers(0, 40, (100, 160, 3), np.uint8)
    frame[5:21, 8:28] = template
    frame[40:64, 70:100] = cv2.resize(template, (30, 24), interpolation=cv2.INTER_LINEAR)
    return frame, template


def test_multiple_scales_recover_original_bounds_and_keep_pixels(scene):
    frame, template = scene
    original_frame, original_template = frame.copy(), template.copy()
    matches = find_scaled(frame, template, .99, scales=(1, 1.5))
    assert {m.region for m in matches} == {Region(8, 5, 20, 16), Region(70, 40, 30, 24)}
    assert all(.99 <= match.score <= 1 for match in matches)
    np.testing.assert_array_equal(frame, original_frame)
    np.testing.assert_array_equal(template, original_template)


def test_explicit_scales_and_search_region_do_not_add_implicit_scale_one(scene):
    frame, template = scene
    result = find_scaled(frame, template, .99, scales=(1.5,))
    assert [m.region for m in result] == [Region(70, 40, 30, 24)]
    result = find_scaled(frame, template, .99, Region(60, 30, 50, 50), scales=(1, 1.5))
    assert [m.region for m in result] == [Region(70, 40, 30, 24)]


def test_single_scale_is_unchanged_and_cross_scale_duplicates_suppressed(scene):
    assert find_scaled(*scene) == find_all(*scene)
    matches = find_scaled(*scene, threshold=.7, scales=(1, 1.01, 1.05, 1.5), max_results=2)
    assert len(matches) == 2
    assert {(m.region.x, m.region.y) for m in matches} == {(8, 5), (70, 40)}


@pytest.mark.parametrize("value", [(), (0,), (4.1,), (True,), (float("nan"),), (float("inf"),), ("1",), [1] * 17, "1"])
def test_invalid_scales(value):
    with pytest.raises(ValueError):
        validate_scales(value)
    with pytest.raises(ValueError):
        Pattern("image.png", scales=value)


def test_pattern_builders_preserve_settings_and_default():
    base = Pattern("image.png").similar(.92).targetOffset(2, -3).inRegion(Region(0, 0, 100, 100))
    scaled = base.atScales(.75, 1, 1.25, 1)
    assert base.scales == (1.,)
    assert scaled.scales == (.75, 1., 1.25)
    assert scaled.region == base.region and scaled.target_offset == base.target_offset
    with pytest.raises(FrozenInstanceError):
        scaled.scales = (1,)


def test_bound_api_scaled_match_and_offset_are_screen_coordinates(scene, tmp_path):
    frame, template = scene
    (tmp_path / "images").mkdir()
    (tmp_path / "images/target.png").write_bytes(cv2.imencode(".png", cv2.cvtColor(template, cv2.COLOR_RGB2BGR))[1].tobytes())
    class Backend:
        serial = "fixture-scaled"
        def capture(self):
            return frame.copy()
        def tap(self, x, y):
            self.last_tap = (x, y)
    backend = Backend()
    device = Device(backend, AssetLibrary(tmp_path))
    pattern = Pattern("target.png").similar(.99).atScales(1.5).targetOffset(2, -3)
    match = device.find(pattern)
    assert match.region == Region(70, 40, 30, 24)
    assert match.device_serial == "fixture-scaled"
    assert device.click(match) == Location(87, 49)
    assert backend.last_tap == (87, 49)


def test_tiny_constant_downsample_is_skipped(scene):
    assert find_scaled(*scene, scales=(.1,), threshold=1) == []


def test_downscale_can_find_template_larger_than_search_image():
    template = np.random.default_rng(43).integers(0, 255, (100, 120, 3), np.uint8)
    resized = cv2.resize(template, (24, 20), interpolation=cv2.INTER_AREA)
    frame = np.zeros((40, 50, 3), np.uint8)
    frame[10:30, 15:39] = resized
    assert find_all(frame, template) == []
    assert [match.region for match in find_scaled(frame, template, .99, scales=(.2,))] == [Region(15, 10, 24, 20)]
