"""Discovery completions must belong to the ADB configuration that started them."""
from types import MethodType, SimpleNamespace

from app.ui.window import StudioWindow


def test_old_adb_reply_cannot_replace_state_after_tool_change():
    calls = []
    old = SimpleNamespace(devices=lambda: ["old"])
    new = SimpleNamespace(devices=lambda: ["new"])
    window = SimpleNamespace(adb=old, discover_pending=False, _closing=False)
    window._submit = lambda operation, callback: calls.append((operation, callback))
    window.refresh_devices = MethodType(StudioWindow.refresh_devices, window)

    window.refresh_devices()
    assert calls[0][0]() == ["old"]
    window.adb = new
    calls[0][1](["old"], None)

    assert len(calls) == 2
    assert calls[1][0]() == ["new"]
    assert window.discover_pending
