"""Recorder persistence, defensive settings and actual RGB recognition."""
import json

import numpy as np
import pytest

from app.automation.api import Device, InvalidCoordinates, Location, Region, use_device
from app.automation.api.context import getPixel, findColor
from app.automation.recording import ActionRecorder
from app.projects.library import AssetLibrary
from app.settings import integer, theme_name
from app.vision.color import pixel, find_color


def test_recorder_roundtrip_is_data_only_and_replaces_transactionally(tmp_path):
    recorder = ActionRecorder()
    recorder.start("fixture-phone", 1)
    recorder.complete(recorder.ticket("fixture-phone", 1, "tap(20, 30)"), 1)
    recorder.stop()
    payload = recorder.session_json()
    loaded = ActionRecorder()
    loaded.load_session(payload)
    assert loaded.actions == ["tap(20, 30)"] and loaded.state == "stopped"
    sentinel = tmp_path / "must-not-execute"
    data = json.loads(payload)
    data["actions"] = [f"open({str(sentinel)!r}, 'w')"]
    loaded.load_session(json.dumps(data))
    assert not sentinel.exists()
    before = loaded.actions.copy()
    data["actions"] = ["tap(1,2)", "not Python!"]
    with pytest.raises(ValueError):
        loaded.load_session(json.dumps(data))
    assert loaded.actions == before


@pytest.mark.parametrize("data", ["not-json", "[]", '{"schema_version":2}', '{"schema_version":1}', "x" * 1_000_001])
def test_invalid_session_documents(data):
    with pytest.raises(ValueError):
        ActionRecorder().load_session(data)


def test_active_recording_cannot_be_replaced_or_saved():
    recorder = ActionRecorder()
    recorder.start("phone", 1)
    with pytest.raises(ValueError):
        recorder.session_json()
    with pytest.raises(ValueError):
        recorder.load_session('{}')


@pytest.mark.parametrize("value,expected", [("4", 4), ("oops", 3), (None, 3), (100, 8), (-1, 1)])
def test_defensive_settings(value, expected):
    class Settings:
        def value(self, key, default):
            return value
    assert integer(Settings(), "limit", 3, 1, 8) == expected
    assert theme_name(Settings()) == "dark"


def scene():
    frame = np.zeros((10, 20, 3), np.uint8)
    frame[3, 5] = [220, 50, 10]
    frame[4, 7] = [222, 48, 11]
    return frame


def test_rgb_tolerance_order_region_and_unchanged_pixels():
    frame = scene()
    before = frame.copy()
    assert pixel(frame, 5, 3) == (220, 50, 10)
    assert find_color(frame, (220, 50, 10)) == [Location(5, 3)]
    assert find_color(frame, (220, 50, 10), 2) == [Location(5, 3), Location(7, 4)]
    assert find_color(frame, (220, 50, 10), 2, Region(6, 3, 5, 4)) == [Location(7, 4)]
    assert find_color(frame, (220, 50, 10), 2, limit=1) == [Location(5, 3)]
    assert find_color(frame, (255,255,255)) == []
    np.testing.assert_array_equal(frame, before)


@pytest.mark.parametrize("color", [(1,2), (256,0,0), (-1,0,0), (True,0,0), "red", None])
def test_invalid_colors(color):
    with pytest.raises(ValueError):
        find_color(scene(), color)


@pytest.mark.parametrize("value", [-1, 256, True, .5, float('nan')])
def test_invalid_tolerance(value):
    with pytest.raises(ValueError):
        find_color(scene(), (1,2,3), value)


def test_bound_pixel_and_color_functions_keep_context_and_typed_coordinate_errors(tmp_path):
    class Backend:
        serial = "fixture-pixels"
        def capture(self):
            return scene()
    device = Device(Backend(), AssetLibrary(tmp_path))
    with use_device(device):
        assert getPixel(5, 3) == (220, 50, 10)
        assert findColor((220, 50, 10), tolerance=2) == [Location(5, 3), Location(7, 4)]
        with pytest.raises(InvalidCoordinates):
            getPixel(100, 3)


@pytest.mark.parametrize("region", [0, False, "screen"])
def test_color_search_does_not_silently_replace_invalid_regions(region):
    with pytest.raises(ValueError, match="region"):
        find_color(scene(), (1,2,3), region=region)


def test_pixel_and_color_api_are_bound_in_independent_spawned_scripts(tmp_path):
    import cv2
    from app.automation.runtime import RuntimeCoordinator
    from test_script_runtime import completed
    path = tmp_path / "color-frame.png"
    path.write_bytes(cv2.imencode(".png", cv2.cvtColor(scene(), cv2.COLOR_RGB2BGR))[1].tobytes())
    source = ("assert getPixel(5, 3) == (220, 50, 10)\n"
              "assert device.findColor((220,50,10), tolerance=2) == [Location(5,3), Location(7,4)]\n"
              "print(getDevice())\n")
    with RuntimeCoordinator(max_workers=2) as runtime:
        ids = [runtime.start(source, serial, trusted=True, project_root=tmp_path,
                             mock_config={"frame_paths": [str(path)]})
               for serial in ("color-one", "color-two")]
        events = completed(runtime, ids)
        assert all(run.state == "completed" for run in runtime.snapshot()), events
        assert len({run.pid for run in runtime.snapshot()}) == 2
        output = "".join(event["text"] for event in events if event.get("event") == "output")
        assert "color-one" in output and "color-two" in output
