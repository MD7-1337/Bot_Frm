"""Library scanning and decoding enforce the same project boundary as scripts."""
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from app.ui.visual_tools import load_asset, scan_assets


def save_png(path):
    image = QImage(20, 16, QImage.Format.Format_RGB32)
    image.fill(QColor("#193f72"))
    assert image.save(str(path), "PNG")


def test_nested_library_scan_skips_escape_and_supports_unicode(tmp_path):
    project = tmp_path / "project"
    (project / "images/nested").mkdir(parents=True)
    save_png(project / "images/nested/cible téléphone.png")
    (project / "images/notes.txt").write_text("not an image")
    save_png(tmp_path / "outside.png")
    (project / "images/escape.png").symlink_to(tmp_path / "outside.png")
    (project / "images/loop").symlink_to(project / "images", target_is_directory=True)
    assert scan_assets(project) == (["images/nested/cible téléphone.png"], False)
    decoded = load_asset(project, "images/nested/cible téléphone.png")
    assert (decoded.width(), decoded.height()) == (20, 16)
    with pytest.raises(ValueError, match="escapes"):
        load_asset(project, "images/escape.png")


def test_missing_images_and_decode_errors_are_explicit(tmp_path):
    assert scan_assets(tmp_path) == ([], False)
    with pytest.raises(FileNotFoundError):
        load_asset(tmp_path, "missing.png")
    (tmp_path / "bad.png").write_bytes(b"not-png")
    with pytest.raises(ValueError, match="raster"):
        load_asset(tmp_path, "bad.png")


def test_library_result_limit(tmp_path):
    (tmp_path / "images").mkdir()
    for index in range(501):
        (tmp_path / "images" / f"{index:03}.png").write_bytes(b"invalid but listed; decoded on selection")
    references, truncated = scan_assets(tmp_path)
    assert len(references) == 500 and truncated
