"""Project lookup contracts; image decoding is exercised by API/preview tests."""
from pathlib import Path

import pytest

from app.projects.library import AssetLibrary, MAX_ASSET_BYTES, discover_project


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "images").mkdir(parents=True)
    (root / "scripts").mkdir()
    return root


def asset(path, content=b"explicit-path-fixture-not-decoded-here"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path.resolve()


def test_basename_library_precedence_and_readonly_properties(project):
    expected = asset(project / "images/start.png")
    asset(project / "scripts/start.png")
    asset(project / "start.png")
    library = AssetLibrary(project, project / "scripts")
    assert library.resolve("start.png") == expected
    assert library.project_root == project.resolve()
    assert library.script_dir == (project / "scripts").resolve()
    assert library.image_root == (project / "images").resolve()
    assert library.roots == (library.image_root, library.script_dir, library.project_root)
    with pytest.raises(AttributeError):
        library.project_root = project.parent


def test_script_and_root_fallback_and_deduplicated_roots(project):
    library = AssetLibrary(project, project / "scripts")
    expected = asset(project / "scripts/local.png")
    asset(project / "local.png")
    assert library.resolve("local.png") == expected
    root_asset = asset(project / "root.PNG")
    assert library.resolve("root.PNG") == root_asset
    assert len(AssetLibrary(project).roots) == 2


def test_explicit_images_path_uses_project_not_script_images(project):
    expected = asset(project / "images/start.png")
    asset(project / "scripts/images/start.png")
    library = AssetLibrary(project, project / "scripts")
    assert library.resolve("images/start.png") == expected
    assert library.resolve(Path("images/start.png")) == expected
    assert library.resolve("images\\start.png") == expected


def test_nested_library_and_script_relative_references(project):
    library = AssetLibrary(project, project / "scripts")
    nested = asset(project / "images/variants/tablet.png")
    assert library.resolve("variants/tablet.png") == nested
    script_relative = asset(project / "scripts/screens/target.png")
    assert library.resolve("screens/target.png") == script_relative


def test_parent_reference_is_script_relative_without_fallback_reinterpretation(project):
    expected = asset(project / "images/start.png")
    library = AssetLibrary(project, project / "scripts")
    assert library.resolve("../images/start.png") == expected
    assert library.resolve("..\\images\\start.png") == expected
    # From project root, ../target.png is outside; do not reinterpret it under
    # images/ to make a traversal appear to be a different contained path.
    asset(project / "target.png")
    with pytest.raises(ValueError, match="escapes"):
        AssetLibrary(project).resolve("../target.png")


def test_absolute_inside_path_and_quoted_unicode_filename(project):
    expected = asset(project / 'images/quote" téléphone 📱.png')
    library = AssetLibrary(project, project / "scripts")
    assert library.resolve(expected) == expected
    assert library.resolve(expected.name) == expected


@pytest.mark.parametrize("reference", ["../../outside.png", "..\\..\\outside.png"])
def test_traversal_outside_is_rejected(project, reference):
    asset(project.parent / "outside.png")
    with pytest.raises(ValueError, match="escapes"):
        AssetLibrary(project, project / "scripts").resolve(reference)


def test_absolute_outside_rejected_even_when_image_exists(project):
    outside = asset(project.parent / "outside.png")
    with pytest.raises(ValueError, match="escapes"):
        AssetLibrary(project).resolve(outside)


@pytest.mark.parametrize("reference", [
    "", "   ", "\x00.png", "a" * 4097 + ".png", "https://example.com/start.png",
    "file:///etc/private.png", "data:image/png;base64,AA==", "start.exe", "start.svg",
    "./private:stream.png", "variants/private:stream.png", "C:\\other\\target.png",
    None, b"start.png", 12,
])
def test_invalid_references(project, reference):
    with pytest.raises(ValueError):
        AssetLibrary(project).resolve(reference)


def test_missing_image_root_and_asset_do_not_mutate_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    library = AssetLibrary(root)
    with pytest.raises(FileNotFoundError, match="missing.png"):
        library.resolve("missing.png")
    assert not (root / "images").exists()


def test_directories_and_oversized_assets_are_not_images(project):
    (project / "images/not-a-file.png").mkdir()
    library = AssetLibrary(project)
    with pytest.raises(ValueError, match="regular file"):
        library.resolve("not-a-file.png")
    oversized = project / "images/too-large.png"
    with oversized.open("wb") as output:
        output.truncate(MAX_ASSET_BYTES + 1)
    with pytest.raises(ValueError, match="16 MiB"):
        library.resolve("too-large.png")
    with oversized.open("wb") as output:
        output.truncate(MAX_ASSET_BYTES)
    assert library.resolve("too-large.png") == oversized.resolve()


def symlink_or_skip(link: Path, target: Path, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("OS/account cannot create symlinks")


def test_symlink_escape_and_in_project_symlink(project):
    outside = asset(project.parent / "outside.png")
    symlink_or_skip(project / "images/escape.png", outside)
    with pytest.raises(ValueError, match="escapes"):
        AssetLibrary(project).resolve("escape.png")
    inside = asset(project / "original.png")
    symlink_or_skip(project / "images/inside.png", inside)
    assert AssetLibrary(project).resolve("inside.png") == inside


def test_symlinked_directory_escape_and_changed_link(project):
    outside = project.parent / "outside"
    outside.mkdir()
    asset(outside / "target.png")
    library = AssetLibrary(project)
    symlink_or_skip(project / "images/linked", outside, directory=True)
    with pytest.raises(ValueError, match="escapes"):
        library.resolve("linked/target.png")
    # Recheck containment per lookup, not only at constructor time.
    image_root = project / "images"
    (image_root / "linked").unlink()
    image_root.rmdir()
    symlink_or_skip(image_root, outside, directory=True)
    with pytest.raises(ValueError, match="escapes"):
        library.resolve("target.png")


def test_invalid_root_and_script_directory(project):
    with pytest.raises(ValueError, match="project_root"):
        AssetLibrary(project / "missing")
    with pytest.raises(ValueError, match="script_dir"):
        AssetLibrary(project, project.parent)
    with pytest.raises(ValueError, match="script_dir"):
        AssetLibrary(project, project / "missing")


def test_discover_nearest_manifest_and_nonexistent_script(project):
    (project / "project.json").write_text("this is intentionally not parsed", encoding="utf-8")
    nested = project / "scripts/subproject"
    nested.mkdir()
    (nested / "project.json").write_text("{}", encoding="utf-8")
    assert discover_project(nested / "not-created.py") == nested
    assert discover_project(project / "scripts/new.py") == project


def test_discover_scripts_ancestor_and_plain_directory(project):
    nested = project / "scripts/helpers"
    nested.mkdir()
    assert discover_project(nested / "new.py") == project
    assert discover_project(project / "plain.py") == project


@pytest.mark.parametrize("value", [None, "", "\0bad.py", 12])
def test_discover_invalid_path(value):
    with pytest.raises(ValueError):
        discover_project(value)
