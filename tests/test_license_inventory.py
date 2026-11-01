"""Artifact provenance rejects mismatched native code and escaping aliases."""
import hashlib
import importlib.util
import json
import runpy
import sys
import types
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location("license_builder", Path(__file__).resolve().parents[1] / "tools/build_windows.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_lgpl_notice_collection_rejects_installed_native_mismatch(tmp_path, monkeypatch):
    wheel = tmp_path / "av.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("av/codec.pyd", b"verified LGPL wheel code")
    installed = tmp_path / "installed/av/codec.pyd"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"different native code")
    manifest = {"source_provenance_complete": True, "external_prefix": False,
                "wheel": str(wheel), "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
    (tmp_path / "lgpl-runtime.json").write_text(json.dumps(manifest))
    class Distribution:
        def locate_file(self, name):
            return tmp_path / "installed" / name
    monkeypatch.setenv("STUDIO_LGPL_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(builder.importlib.metadata, "distribution", lambda _: Distribution())
    with pytest.raises(ValueError, match="differs from verified LGPL wheel"):
        builder.collect_lgpl_notices(tmp_path / "notices")
    assert not (tmp_path / "notices").exists()


def test_payload_inventory_hashes_real_files_and_remains_blocked(tmp_path, monkeypatch):
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "native.dll").write_bytes(b"actual native file")
    monkeypatch.setattr(builder, "source_commit", lambda: "fixture")
    result = builder.write_payload_inventory(payload, tmp_path / "report.json")
    assert result["redistribution_approved"] is False
    assert result["files"] == [{"path": "native.dll", "bytes": 18,
                                "sha256": hashlib.sha256(b"actual native file").hexdigest()}]
    assert "Application distribution license" in result["blockers"][0]


@pytest.mark.parametrize("relative", [
    "_internal/PySide6/Qt6Charts.dll",
    "_internal/PySide6/Qt/Qt6DataVisualization.dll",
    "_internal/PySide6/Qt/lib/libQt6Graphs.so.6",
    "_internal/PySide6/QtCharts.abi3.so",
    "_internal/PySide6/QtGraphsWidgets.pyd",
    "_internal/PySide6/Qt/qml/QtGraphs/libgraphsplugin.so",
    "_internal/PySide6/QT6CHARTS.DLL",
    "_internal/PySide6/Qt/lib/libQt6VirtualKeyboard.so.6",
    "_internal/PySide6/QtVirtualKeyboard.pyd",
    "_internal/PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so",
])
def test_payload_rejects_unused_gpl_qt_modules_after_retaining_evidence(tmp_path, monkeypatch, relative):
    payload = tmp_path / "payload"
    module = payload / relative
    module.parent.mkdir(parents=True)
    module.write_bytes(b"unintended module")
    destination = tmp_path / "inventory.json"
    monkeypatch.setattr(builder, "source_commit", lambda: "fixture")
    with pytest.raises(ValueError, match="Unused GPL-only Qt modules"):
        builder.write_payload_inventory(payload, destination)
    report = json.loads(destination.read_text())
    assert report["redistribution_approved"] is False
    assert report["unexpected_gpl_qt_paths"] == [relative]
    assert report["files"][0]["sha256"] == hashlib.sha256(b"unintended module").hexdigest()
    assert "Unused GPL-only Qt" in report["blockers"][-1]


def test_payload_guard_preserves_required_native_dependencies_and_reference_text(tmp_path, monkeypatch):
    payload = tmp_path / "payload"
    payload.mkdir()
    for filename in ("libQt6Qml.so.6", "Qt6Quick.dll", "Qt6WebEngineCore.dll", "Qt6Charts-review.txt"):
        (payload / filename).write_bytes(b"fixture")
    monkeypatch.setattr(builder, "source_commit", lambda: "fixture")
    result = builder.write_payload_inventory(payload, tmp_path / "inventory.json")
    assert result["unexpected_gpl_qt_paths"] == []
    assert len(result["files"]) == 4


def test_qtgui_hook_filters_only_virtual_keyboard_before_native_scanning(monkeypatch):
    entries = [
        ("/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so", "PySide6/Qt/plugins/platforminputcontexts"),
        (r"C:\Qt\plugins\platforminputcontexts\qtvirtualkeyboardplugin.dll", "PySide6/plugins/platforminputcontexts"),
        ("/Qt/plugins/platforminputcontexts/libibusplatforminputcontextplugin.so", "platforminputcontexts"),
        ("/Qt/plugins/platforminputcontexts/libfcitx5platforminputcontextplugin.so", "platforminputcontexts"),
        ("/Qt/plugins/platforms/libqxcb.so", "platforms"),
        (r"C:\Qt\plugins\platforms\qwindows.dll", "platforms"),
    ]
    # Source testing does not require the optional freezer build dependency.
    for name in ("PyInstaller", "PyInstaller.utils", "PyInstaller.utils.hooks", "PyInstaller.utils.hooks.qt"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    qt_hooks = sys.modules["PyInstaller.utils.hooks.qt"]
    qt_hooks.add_qt6_dependencies = lambda _: (["required.module"], entries, [("resource", "data")])
    hook = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging/hooks/hook-PySide6.QtGui.py"))
    assert hook["binaries"] == entries[2:]
    assert hook["hiddenimports"] == ["required.module"]
    assert hook["datas"] == [("resource", "data")]
