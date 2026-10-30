"""Computer-vision checks use synthetic pixels, not claims of phone validation."""
import dataclasses

import numpy as np
import pytest

from app.vision.matching import ImageNotFound, Location, Match, Region, find, find_all


@pytest.fixture
def images():
    rng = np.random.default_rng(421)
    frame = rng.integers(0, 120, (100, 140, 3), dtype=np.uint8)
    template = rng.integers(0, 256, (12, 16, 3), dtype=np.uint8)
    frame[20:32, 30:46] = template
    frame[65:77, 100:116] = template
    return frame, template


def test_two_targets_are_found_and_pixels_are_unchanged(images):
    frame, template = images
    before_frame, before_template = frame.copy(), template.copy()
    matches = find_all(frame, template, threshold=0.99)
    assert {(m.region.x, m.region.y) for m in matches} == {(30, 20), (100, 65)}
    assert all(0.99 <= m.score <= 1 for m in matches)
    assert matches[0].score >= matches[1].score
    np.testing.assert_array_equal(frame, before_frame)
    np.testing.assert_array_equal(template, before_template)


def test_search_region_restores_full_screen_coordinates(images):
    frame, template = images
    matches = find_all(frame, template, region=Region(80, 50, 60, 50))
    assert len(matches) == 1
    assert matches[0].region == Region(100, 65, 16, 12)
    assert matches[0].target == Location(108, 71)


def test_search_region_excludes_both_targets(images):
    frame, template = images
    assert find_all(frame, template, region=Region(0, 0, 25, 50)) == []
    with pytest.raises(ImageNotFound, match="No image match"):
        find(frame, template, region=Region(0, 0, 25, 50))


def test_result_limit_and_best_match(images):
    frame, template = images
    assert len(find_all(frame, template, max_results=1)) == 1
    assert isinstance(find(frame, template), Match)


def test_oversized_template_returns_no_results(images):
    frame, template = images
    assert find_all(frame, template, region=Region(0, 0, 5, 5)) == []


def test_nonmaximum_suppression_removes_clustered_matches():
    # A repeated gradient produces many nearby high scores. NMS must suppress
    # overlapping detections, while preserving distant identical copies.
    gradient = np.tile(np.arange(20, dtype=np.uint8)[None, :, None] * 10, (20, 1, 3))
    frame = np.zeros((60, 100, 3), dtype=np.uint8)
    frame[10:30, 10:30] = gradient
    frame[10:30, 65:85] = gradient
    matches = find_all(frame, gradient, threshold=0.99)
    assert len(matches) == 2
    assert {(m.region.x, m.region.y) for m in matches} == {(10, 10), (65, 10)}


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -0.1, 1.1, True, "0.9"])
def test_invalid_threshold(images, threshold):
    with pytest.raises(ValueError, match="threshold"):
        find_all(*images, threshold=threshold)


@pytest.mark.parametrize("setting", [0, -1, 10001, 1.5, True])
def test_invalid_result_limit(images, setting):
    with pytest.raises(ValueError, match="max_results"):
        find_all(*images, max_results=setting)


@pytest.mark.parametrize("setting", [float("nan"), -1, 1, 2, True])
def test_invalid_iou(images, setting):
    with pytest.raises(ValueError, match="nms_iou"):
        find_all(*images, nms_iou=setting)


def test_constant_template_is_rejected(images):
    frame, _ = images
    # Distinct constant channel colours still have no spatial information.
    constant = np.empty((5, 5, 3), dtype=np.uint8)
    constant[:] = [10, 80, 120]
    with pytest.raises(ValueError, match="constant"):
        find_all(frame, constant)


@pytest.mark.parametrize("bad", [np.zeros((4, 4)), np.zeros((4, 4, 3)), np.zeros((0, 4, 3), dtype=np.uint8), None])
def test_invalid_image_shape_or_dtype(images, bad):
    frame, template = images
    with pytest.raises(ValueError):
        find_all(bad, template)
    with pytest.raises(ValueError):
        find_all(frame, bad)


def test_out_of_bounds_region_is_not_silently_clipped(images):
    with pytest.raises(ValueError, match="outside"):
        find_all(*images, region=Region(100, 90, 50, 50))


@pytest.mark.parametrize("args", [(-1, 0, 5, 5), (0, 0, 0, 5), (0, 0, 5, -1), (True, 0, 5, 5)])
def test_invalid_region(args):
    with pytest.raises(ValueError):
        Region(*args)


def test_match_metadata_is_immutable():
    match = Match(Region(10, 10, 5, 5), 0.98)
    with pytest.raises(dataclasses.FrozenInstanceError):
        match.score = 0.5
