import pytest

from app.streaming.coordinates import Viewport


def test_portrait_fit_rejects_letterbox_and_exclusive_bounds():
    viewport = Viewport(100, 200, 400, 400)
    assert viewport.content_rect == (100, 0, 200, 400)
    assert viewport.to_device(99.99, 150) is None
    assert viewport.to_device(300, 150) is None
    assert viewport.to_device(100, 400) is None
    assert viewport.to_device(100, 0) == (0, 0)
    assert viewport.to_device(299.99, 399.99) == (99, 199)


@pytest.mark.parametrize("rotation,corner", [(0, (0, 0)), (90, (0, 19)), (180, (9, 19)), (270, (9, 0))])
def test_rotated_top_left_corresponds_to_source_pixel(rotation, corner):
    viewport = Viewport(10, 20, 600, 500, rotation)
    left, top, _, _ = viewport.content_rect
    assert viewport.to_device(left, top) == corner


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("view_size", [(301, 189), (400, 400), (31, 10)])
def test_every_pixel_roundtrips_including_rotations_and_fractional_scale(rotation, view_size):
    viewport = Viewport(13, 29, *view_size, rotation)
    for x in range(13):
        for y in range(29):
            assert viewport.to_device(*viewport.from_device(x, y)) == (x, y)


@pytest.mark.parametrize("x,y", [(float("nan"), 1), (1, float("inf")), (-1, -1)])
def test_nonfinite_and_outside_pointer_rejected(x, y):
    assert Viewport(10, 10, 10, 10).to_device(x, y) is None


@pytest.mark.parametrize("values", [(0, 1, 1, 1), (1, -1, 1, 1), (1, 1, 0, 1), (1, 1, 1, 1, 45)])
def test_invalid_viewport(values):
    with pytest.raises(ValueError):
        Viewport(*values)


def test_source_pixel_validation():
    with pytest.raises(ValueError):
        Viewport(10, 10, 20, 20).from_device(10, 5)
