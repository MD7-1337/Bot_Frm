import ast
import base64
import json
import inspect
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtGui import QColor, QImage
import pytest

from app.automation.api import API_METHOD_NAMES, Device
from app.editor.bridge import EditorBridge, image_references
from app.editor.catalog import api_catalog


def save_image(path, width=20, height=12):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#537bc1"))
    assert image.save(str(path), "PNG")


def test_catalog_is_the_public_implementation_contract():
    catalog = api_catalog()
    methods = {item["name"]: item for item in catalog if item["member_of"] == "device"}
    assert set(methods) == set(API_METHOD_NAMES)
    assert all(item["documentation"] and "self" not in item["signature"] for item in methods.values())
    assert "timeout" in methods["waitImage"]["signature"]
    assert "duration" in methods["longPress"]["signature"]
    assert {item["name"] for item in catalog if item["kind"] == "type"} >= {"Pattern", "Region", "Location", "Match"}
    assert {item["name"] for item in catalog if item["member_of"] == "Pattern"} == {"similar", "targetOffset", "inRegion"}
    assert methods["click"]["documentation"] == inspect.getdoc(Device.click)


def test_ast_image_references_preserve_python_and_utf16_columns(tmp_path):
    source = '"📱é"; click("start.png")\nimage_path = "téléphone.png"\n# "comment.png"\nwait(2)\n'
    before = source
    items = image_references(source)
    assert {item["reference"] for item in items} == {"téléphone.png", "start.png"}
    first = next(item for item in items if item["reference"] == "start.png")
    prefix = source.splitlines()[0].split('"start.png"')[0]
    assert first["start_column"] == len(prefix.encode("utf-16-le")) // 2 + 1
    assert source == before
    ast.parse(source)
    sentinel = tmp_path / "never-executed"
    image_references(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\nclick('x.png')")
    assert not sentinel.exists()


def test_image_reference_limits_and_invalid_python():
    assert image_references("if:\n 'x.png'") == []
    assert image_references("x" * 1_000_001) == []
    assert len(image_references("\n".join(f"x{i}='a{i}.png'" for i in range(200)))) == 128


def test_bridge_thumbnails_are_bounded_and_project_contained(tmp_path):
    root = tmp_path / "project"
    images = root / "images"
    images.mkdir(parents=True)
    save_image(images / "téléphone.png", 32, 3200)
    bridge = EditorBridge()
    bridge.set_project_root(root)
    preview = json.loads(bridge.imagePreview("téléphone.png"))
    assert preview["available"] and (preview["width"], preview["height"]) == (32, 3200)
    raw = base64.b64decode(preview["data_url"].split(",", 1)[1])
    assert raw.startswith(b"\x89PNG")
    thumbnail = QImage.fromData(raw, "PNG")
    assert thumbnail.width() <= 256 and thumbnail.height() <= 256
    outside = tmp_path / "outside.png"
    save_image(outside)
    for reference in (str(outside), "../outside.png", "https://example.com/private.png", "../../etc/passwd", "missing.png"):
        assert not json.loads(bridge.imagePreview(reference))["available"]
    with pytest.raises(ValueError):
        bridge.set_project_root(root, tmp_path)


def test_missing_warnings_preview_refresh_and_host_only_root(tmp_path):
    (tmp_path / "images").mkdir()
    path = tmp_path / "images/a.png"
    bridge = EditorBridge()
    bridge.set_project_root(tmp_path)
    references = json.loads(bridge.imageReferences('click("a.png")\nwait("missing.png")'))
    assert all(not item["available"] for item in references)
    save_image(path, 30, 20)
    one = json.loads(bridge.imagePreview("a.png"))
    references = json.loads(bridge.imageReferences('click("a.png")'))
    assert references[0]["available"]
    save_image(path, 40, 21)
    two = json.loads(bridge.imagePreview("a.png"))
    assert one["width"] == 30 and two["width"] == 40
    assert json.loads(bridge.imagePreview("images/a.png"))["reference"] == "images/a.png"
    meta = bridge.metaObject()
    assert meta.indexOfMethod("apiCatalog()") >= 0
    assert meta.indexOfMethod("imagePreview(QString)") >= 0
    assert meta.indexOfMethod("set_project_root(QString)") == -1
    assert meta.indexOfMethod("execute(QString)") == -1


def test_invalid_image_and_preview_pixel_limits(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images/broken.png").write_bytes(b"not an image")
    save_image(tmp_path / "images/too-large.png", 4097, 4096)
    bridge = EditorBridge()
    bridge.set_project_root(tmp_path)
    assert not json.loads(bridge.imagePreview("broken.png"))["available"]
    assert not json.loads(bridge.imagePreview("too-large.png"))["available"]
    bridge.set_project_root(None)
    assert not json.loads(bridge.imagePreview("broken.png"))["available"]


def test_preview_rejects_nonraster_content_disguised_as_png(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images/disguised.png").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30">'
        '<rect width="40" height="30" fill="red"/></svg>', encoding="utf-8")
    bridge = EditorBridge()
    bridge.set_project_root(tmp_path)
    result = json.loads(bridge.imagePreview("disguised.png"))
    assert not result["available"] and "data_url" not in result


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Opt-in real Qt WebEngine scripting integration")
def test_actual_monaco_api_images_signatures_and_execution_line(tmp_path):
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, str(root / "tools/probe_script_editor.py"), str(tmp_path)],
                               cwd=root, capture_output=True, text=True, timeout=35)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    for name in ("catalog", "completion", "signature", "image_hover", "missing_warning", "execution_line", "plain_python"):
        assert f'"{name}": true' in completed.stdout
