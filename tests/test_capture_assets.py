import ast
from pathlib import Path

import pytest

from app.projects.assets import android_region, reference_code
from app.vision.matching import Region


def test_scaled_region_rounds_outward_and_stays_in_screen():
    assert android_region(Region(1, 1, 3, 4), (7, 11), (21, 33)) == Region(3, 3, 9, 12)
    assert android_region(Region(6, 10, 1, 1), (7, 11), (20, 30)) == Region(17, 27, 3, 3)
    assert android_region(Region(0, 0, 7, 11), (7, 11), (20, 30)) == Region(0, 0, 20, 30)


@pytest.mark.parametrize("region,image_size,source_size", [
    (Region(1, 1, 10, 10), (10, 10), (20, 20)),
    (Region(0, 0, 1, 1), (0, 10), (20, 20)),
    (Region(0, 0, 1, 1), (10, 10), (20, False)),
    (None, (10, 10), (20, 20)),
])
def test_bad_regions_sizes_rejected(region, image_size, source_size):
    with pytest.raises(ValueError):
        android_region(region, image_size, source_size)


def test_relative_reference_is_plain_safe_python(tmp_path):
    script_dir = tmp_path / "scripts"
    path = tmp_path / 'images' / 'quote" téléphone.png'
    code = reference_code(path, script_dir)
    tree = ast.parse(code)
    assert isinstance(tree.body[0], ast.Assign)
    assert ast.literal_eval(tree.body[0].value) == '../images/quote" téléphone.png'
    assert len(tree.body) == 1


def test_filename_cannot_inject_python(tmp_path):
    path = tmp_path / 'x"; print("executed").png'
    tree = ast.parse(reference_code(path))
    assert len(tree.body) == 1
    assert ast.literal_eval(tree.body[0].value) == str(path.resolve())


def test_absolute_reference_without_script_directory(tmp_path):
    path = tmp_path / "target.png"
    value = ast.literal_eval(ast.parse(reference_code(path)).body[0].value)
    assert Path(value) == path.resolve()
