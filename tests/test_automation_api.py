"""Real OpenCV/image-library API tests with explicitly bound fixture backends."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path
import threading
from typing import get_type_hints

import cv2
import numpy as np
import pytest

from app.automation import api
from app.automation.api import (
    AmbiguousMatch, AssetNotFound, Cancelled, CrossDeviceTarget, Device,
    DeviceDisconnected, FrameUnavailable, ImageNotFound, InvalidAsset,
    InvalidCoordinates, Location, Match, NoExecutionContext, Offset, Pattern,
    RecognitionTimeout, Region, Screen,
)
from app.automation.backends import MockBackend
from app.projects.library import AssetLibrary


class FixtureBackend:
    """Owned RGB frames and recorded calls; never a production connection."""
    def __init__(self, frames, serial="fixture-one"):
        self.serial = serial
        self.frames = list(frames)
        self.captures = 0
        self.actions = []
        self.capture_error = None
        self.on_capture = None

    def capture(self):
        if self.capture_error:
            raise self.capture_error
        if self.on_capture:
            self.on_capture()
        index = min(self.captures, len(self.frames) - 1)
        self.captures += 1
        return self.frames[index].copy()

    def tap(self, x, y):
        self.actions.append(("tap", x, y))

    def swipe(self, x1, y1, x2, y2, duration_ms=500):
        self.actions.append(("swipe", x1, y1, x2, y2, duration_ms))

    def key(self, key):
        self.actions.append(("key", key))

    def launch_app(self, package):
        self.actions.append(("launch", package))

    def stop_app(self, package):
        self.actions.append(("stop", package))

    def type_text(self, text):
        self.actions.append(("text", text))


def save_rgb(path, image):
    success, data = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    assert success
    path.write_bytes(data.tobytes())


@pytest.fixture
def scene(tmp_path):
    (tmp_path / "images").mkdir()
    rng = np.random.default_rng(214)
    template = rng.integers(0, 256, (11, 9, 3), dtype=np.uint8)
    base = rng.integers(0, 30, (80, 100, 3), dtype=np.uint8)
    one = base.copy()
    one[30:41, 20:29] = template
    two = one.copy()
    two[50:61, 70:79] = template
    path = tmp_path / "images" / "start téléphone.png"
    save_rgb(path, template)
    return tmp_path, template, base, one, two, path.name


def device_for(scene, frames=None, *, serial="fixture-one", checkpoint=None, wait=None, emit=None):
    root, _, _, one, _, _ = scene
    backend = FixtureBackend(frames if frames is not None else [one], serial)
    device = Device(backend, AssetLibrary(root), checkpoint=checkpoint,
                    interruptible_wait=wait, emit=emit)
    return device, backend


def test_find_pattern_offset_region_and_click_use_actual_pixels(scene):
    device, backend = device_for(scene)
    name = scene[-1]
    original = Pattern(name)
    pattern = original.similar(.99).inRegion(Region(10, 20, 40, 30)).targetOffset(3, -2)
    assert original.similarity == .85 and original.region is None and original.target_offset == Offset()
    match = device.find(pattern)
    assert match.region == Region(20, 30, 9, 11)
    assert match.score > .999
    assert match.device_serial == "fixture-one" and match.source_size == (100, 80)
    assert match.target == Location(27, 33)
    assert device.click(match) == Location(27, 33)
    assert backend.actions == [("tap", 27, 33)]


def test_multiple_targets_require_deliberate_find_all(scene):
    device, backend = device_for(scene, [scene[4]])
    matches = device.findAll(Pattern(scene[-1]).similar(.99))
    assert {m.region for m in matches} == {Region(20, 30, 9, 11), Region(70, 50, 9, 11)}
    assert all(a.score >= b.score for a, b in zip(matches, matches[1:]))
    assert len(device.findAll(scene[-1], limit=1)) == 1
    for operation in (device.find, device.exists, device.click):
        with pytest.raises(AmbiguousMatch):
            operation(scene[-1])
    assert backend.actions == []
    assert device.find(scene[-1], region=Region(65, 45, 20, 20)).region.x == 70


def test_missing_match_is_distinct_from_missing_asset_and_transport(scene):
    device, backend = device_for(scene, [scene[2]])
    assert device.exists(scene[-1]) is None
    with pytest.raises(ImageNotFound):
        device.find(scene[-1])
    with pytest.raises(AssetNotFound):
        device.exists("missing.png")
    backend.capture_error = DeviceDisconnected("fixture cable removed")
    with pytest.raises(DeviceDisconnected):
        device.exists(scene[-1])
    with pytest.raises(DeviceDisconnected):
        device.waitVanish(scene[-1], timeout=0)


@pytest.mark.parametrize("data", [b"", b"not an image"])
def test_malformed_template_has_typed_error(scene, data):
    root = scene[0]
    (root / "images/broken.png").write_bytes(data)
    device, backend = device_for(scene)
    with pytest.raises(InvalidAsset):
        device.find("broken.png")
    assert not backend.actions


def test_constant_template_and_unsafe_references_are_not_absence(scene):
    save_rgb(scene[0] / "images/flat.png", np.full((5, 5, 3), 80, np.uint8))
    device, _ = device_for(scene)
    for reference in ("flat.png", "../../escape.png"):
        with pytest.raises(InvalidAsset):
            device.exists(reference)


def test_regions_and_offsets_outside_screen_never_dispatch(scene):
    device, backend = device_for(scene)
    with pytest.raises(InvalidCoordinates):
        device.find(scene[-1], region=Region(99, 0, 2, 2))
    with pytest.raises(ValueError):
        device.find(Pattern(scene[-1]).inRegion(Region(0, 0, 50, 50)), region=Region(0, 0, 80, 80))
    with pytest.raises(InvalidCoordinates):
        device.click(Pattern(scene[-1]).targetOffset(-90, 0))
    assert backend.actions == []


def test_foreign_match_and_changed_geometry_are_rejected(scene):
    one, first_backend = device_for(scene)
    two, second_backend = device_for(scene, serial="fixture-two")
    match = one.find(scene[-1])
    with pytest.raises(CrossDeviceTarget):
        two.click(match)
    assert second_backend.captures == 0 and not second_backend.actions
    first_backend.frames = [np.zeros((160, 200, 3), np.uint8)]
    with pytest.raises(InvalidCoordinates):
        one.click(match)
    assert first_backend.actions == []


def test_changed_backend_identity_cannot_redirect_short_functions(scene):
    device, backend = device_for(scene)
    backend.serial = "another-phone"
    with pytest.raises(CrossDeviceTarget):
        device.tap(1, 2)
    assert not backend.actions and backend.captures == 0
    with pytest.raises(AttributeError):
        device.serial = "another-phone"


@pytest.mark.parametrize("coordinates", [(-1, 0), (0, -1), (100, 0), (0, 80), (True, 2), (1.5, 2), (2**1000, 2)])
def test_tap_validates_actual_screen_bounds(scene, coordinates):
    device, backend = device_for(scene)
    with pytest.raises(InvalidCoordinates):
        device.tap(*coordinates)
    assert backend.actions == []


def test_touch_actions_share_implementation_and_cancellable_second_tap(scene):
    device, backend = device_for(scene, wait=lambda seconds: None)
    assert device.click((4, 5)) == Location(4, 5)
    assert device.click(Location(6, 7)) == Location(6, 7)
    assert device.doubleClick((8, 9), interval=.01) == Location(8, 9)
    assert device.longPress((10, 11), duration=.7) == Location(10, 11)
    device.swipe(1, 2, 3, 4, duration=.2)
    device.drag(4, 3, 2, 1, duration=.3)
    assert backend.actions == [
        ("tap", 4, 5), ("tap", 6, 7), ("tap", 8, 9), ("tap", 8, 9),
        ("swipe", 10, 11, 10, 11, 700), ("swipe", 1, 2, 3, 4, 200),
        ("swipe", 4, 3, 2, 1, 300),
    ]
    def cancelled_wait(seconds):
        raise Cancelled("stop between taps")
    device._interruptible_wait = cancelled_wait
    with pytest.raises(Cancelled):
        device.doubleClick((12, 13))
    assert backend.actions[-1] == ("tap", 12, 13)
    assert backend.actions.count(("tap", 12, 13)) == 1


def test_double_click_stops_if_source_geometry_changes_between_taps(scene):
    device, backend = device_for(scene, [scene[3], np.zeros((100, 120, 3), np.uint8)], wait=lambda _: None)
    with pytest.raises(InvalidCoordinates, match="resolution changed"):
        device.doubleClick((3, 4))
    assert backend.actions == [("tap", 3, 4)]


@pytest.mark.parametrize("direction,expected", [
    ("up", (50, 60, 50, 20)), ("down", (50, 20, 50, 60)),
    ("left", (75, 40, 25, 40)), ("right", (25, 40, 75, 40)),
])
def test_scroll_is_explicit_directional_adb_gesture(scene, direction, expected):
    device, backend = device_for(scene)
    device.scroll(direction, amount=2)
    assert backend.actions == [("swipe", *expected, 350)] * 2


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, 2**10000])
def test_nonfinite_or_invalid_durations_never_dispatch(scene, value):
    device, backend = device_for(scene)
    for call in (lambda: device.sleep(value), lambda: device.swipe(1, 2, 3, 4, duration=value),
                 lambda: device.longPress((1, 2), value), lambda: device.doubleClick((1, 2), value)):
        with pytest.raises(ValueError):
            call()
    assert backend.actions == []


def test_screen_owns_pixels_and_reports_original_resolution(scene):
    device, backend = device_for(scene)
    screen = device.capture()
    assert isinstance(screen, Screen) and screen.resolution == (100, 80)
    assert device.getResolution() == (100, 80)
    assert np.array_equal(screen.to_numpy(), scene[3])
    assert not screen.to_numpy().flags.writeable
    backend.frames[0][0, 0] = 0
    assert np.array_equal(screen.to_numpy()[1, 1], scene[3][1, 1])
    with pytest.raises(ValueError):
        screen.to_numpy()[1, 1] = 0
    with pytest.raises(FrozenInstanceError):
        screen.width = 1


@pytest.mark.parametrize("frame", [np.empty((0, 2, 3), np.uint8), np.zeros((2, 2, 4), np.uint8), np.zeros((2, 2, 3), float)])
def test_invalid_frame_is_not_recognition_absence(scene, frame):
    device, _ = device_for(scene, [frame])
    with pytest.raises(FrameUnavailable):
        device.capture()


def test_android_controls_and_success_events_keep_serial_context(scene):
    events = []
    device, backend = device_for(scene, emit=lambda kind, **fields: events.append((kind, fields)))
    device.back()
    device.home()
    device.launchApp("com.example.app")
    device.stopApp("com.example.app")
    device.typeText("hello world")
    device.find(scene[-1])
    assert backend.actions == [("key", "KEYCODE_BACK"), ("key", "KEYCODE_HOME"),
                               ("launch", "com.example.app"), ("stop", "com.example.app"), ("text", "hello world")]
    assert len([event for event in events if event[0] == "action"]) == 5
    assert events[-1][0] == "recognition" and events[-1][1]["count"] == 1
    assert events[-1][1]["matches"][0]["x"] == 20


def test_both_styles_and_nested_contexts_never_share_current_phone(scene):
    one, first = device_for(scene)
    two, second = device_for(scene, serial="fixture-two")
    with pytest.raises(NoExecutionContext):
        api.getDevice()
    with api.use_device(one):
        api.tap(1, 2)
        assert api.getDevice() == "fixture-one"
        with api.use_device(two):
            api.click((3, 4))
            assert api.getDevice() == "fixture-two"
        assert api.getDevice() == "fixture-one"
        one.click((5, 6))
    assert first.actions == [("tap", 1, 2), ("tap", 5, 6)]
    assert second.actions == [("tap", 3, 4)]
    with pytest.raises(NoExecutionContext):
        api.tap(1, 2)
    bindings = one.bindings()
    assert bindings["device"] is one
    assert set(api.API_METHOD_NAMES) <= bindings.keys()


def test_contextvars_do_not_inherit_another_threads_device(scene):
    one, _ = device_for(scene)
    observed = []
    with api.use_device(one):
        def check():
            try:
                api.getDevice()
            except NoExecutionContext:
                observed.append("unassigned")
        thread = threading.Thread(target=check)
        thread.start()
        thread.join(2)
    assert observed == ["unassigned"]


def test_mock_transport_is_explicit_and_unsupported_text_is_not_success(scene):
    device = Device(MockBackend("fixture-phone", {"resolution": [100, 80]}), AssetLibrary(scene[0]))
    assert device.getResolution() == (100, 80)
    with pytest.raises(api.UnsupportedCapability):
        device.typeText("héllo")


@pytest.mark.parametrize("kwargs", [{"similarity": -1}, {"similarity": 1.01},
                                    {"similarity": float("nan")}, {"similarity": 2**10000},
                                    {"region": "invalid"}, {"target_offset": (1, 2)}])
def test_pattern_metadata_is_validated_and_immutable(kwargs):
    with pytest.raises(ValueError):
        Pattern("start.png", **kwargs)
    with pytest.raises(FrozenInstanceError):
        Pattern("start.png").path = "other.png"


@pytest.mark.parametrize("path", ["", "bad\0.png", "x" * 4097])
def test_invalid_pattern_reference_is_typed(path):
    with pytest.raises(InvalidAsset):
        Pattern(path)


def test_model_bounds_are_clear_to_scripts():
    with pytest.raises(ValueError):
        Location(-1, 0)
    with pytest.raises(ValueError):
        Region(0, 0, 0, 10)
    with pytest.raises(ValueError):
        Offset(True, 0)
    with pytest.raises(InvalidCoordinates):
        Match(Region(8, 8, 4, 4), .9, "phone", (10, 10), "frame", "image.png")
    with pytest.raises(ValueError):
        Screen("phone", bytes(12), 2, 2, "frame", 2**10000)


def test_invalid_gesture_arguments_never_dispatch(scene):
    device, backend = device_for(scene)
    calls = [lambda: device.swipe(0, 0, 1, 1, 0),
             lambda: device.longPress((1, 1), 0),
             lambda: device.swipe(0, 0, 100, 1),
             lambda: device.scroll("diagonal"), lambda: device.scroll("up", True),
             lambda: device.scroll("up", 0), lambda: device.scroll("up", 101),
             lambda: device.findAll(scene[-1], limit=True),
             lambda: device.findAll(scene[-1], limit=0),
             lambda: device.click(object())]
    for call in calls:
        with pytest.raises((ValueError, TypeError)):
            call()
    assert not backend.actions


def test_exception_handling_and_normal_python_are_ordinary_code(scene):
    device, backend = device_for(scene)
    namespace = device.bindings()
    source = '''
import math
def action(index):
    if index == 0:
        tap(1, 2)
    elif index == 1:
        device.click(Location(3, 4))
    else:
        assert math.sqrt(9) == 3
for index in range(3):
    action(index)
count = 0
while count < 2:
    count += 1
try:
    find("missing.png")
except AssetNotFound:
    recovered = True
'''
    with api.use_device(device):
        exec(compile(source, "<explicit-api-fixture>", "exec"), namespace, namespace)
    assert namespace["recovered"] and namespace["count"] == 2
    assert backend.actions == [("tap", 1, 2), ("tap", 3, 4)]


@pytest.mark.parametrize("name", api.API_METHOD_NAMES)
def test_public_short_function_signatures_match_bound_methods_without_self(scene, name):
    device, _ = device_for(scene)
    function = getattr(api, name)
    exposed = inspect.signature(function)
    expected = inspect.signature(getattr(device, name), eval_str=True)
    assert "self" not in exposed.parameters
    assert exposed == expected
    assert function.__qualname__ == name
    assert get_type_hints(function) == get_type_hints(getattr(Device, name))


def test_public_type_hints_resolve_targets_screens_and_wait_overloads():
    assert list(inspect.signature(api.click).parameters) == ["target"]
    assert get_type_hints(api.click) == {"target": api.Target, "return": Location}
    assert list(inspect.signature(api.wait).parameters) == ["target", "timeout"]
    assert get_type_hints(api.wait)["return"] == Match | None
    assert inspect.signature(api.capture).parameters == {}
    assert get_type_hints(api.capture) == {"return": Screen}


def test_text_action_metadata_does_not_copy_sensitive_input(scene):
    events = []
    device, backend = device_for(scene, emit=lambda kind, **fields: events.append((kind, fields)))
    private_text = "fixture-password-2041"
    assert device.typeText(private_text) is None
    assert backend.actions == [("text", private_text)]
    assert events == [("action", {"command": "type_text", "arguments": {"characters": len(private_text)}})]
    assert private_text not in repr(events)
