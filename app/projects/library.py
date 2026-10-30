"""Project-contained image lookup shared by scripting and editor previews.

Resolution never creates files, changes the current directory, downloads a URL,
or executes a project manifest. Containment is checked against canonical paths
on every lookup, including paths reached through symlinks. It is a filesystem
lookup boundary, not an OS sandbox against concurrent filesystem mutation.
"""
from __future__ import annotations

import errno
from pathlib import Path
import re
import stat

MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_REFERENCE_CHARS = 4096
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".webp"})
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _directory(value: str | Path, name: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value) or "\x00" in str(value):
        raise ValueError(f"{name} must be an existing directory")
    try:
        resolved = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{name} must be an existing directory") from error
    if not resolved.is_dir():
        raise ValueError(f"{name} must be an existing directory")
    return resolved


def _contained(path: Path, root: Path) -> Path:
    try:
        canonical = path.resolve(strict=False)
    except (RuntimeError, ValueError) as error:
        raise ValueError("Image reference cannot be resolved safely") from error
    except OSError as error:
        if error.errno in (errno.ENAMETOOLONG, errno.ELOOP):
            raise ValueError("Image reference is too long or contains a symlink loop") from error
        raise
    if not canonical.is_relative_to(root):
        raise ValueError("Image reference escapes the selected project")
    return canonical


class AssetLibrary:
    """Resolve local image references within one explicitly selected project.

    Bare names prefer ``project/images``, followed by the script directory and
    project root. ``images/...`` is explicitly project-relative. Other relative
    names try script-relative, image-library-relative, then project-relative
    lookup. References containing ``..`` have only their explicit script-relative
    meaning, avoiding surprising reinterpretation by fallback search paths.

    Absolute paths are accepted only inside the project. Returned files are
    canonical regular image paths of at most 16 MiB. Missing assets raise
    FileNotFoundError; unsafe/malformed references raise ValueError. Actual image
    decoding is left to the recognition/preview consumer.
    """

    def __init__(self, project_root: str | Path, script_dir: str | Path | None = None):
        self._project_root = _directory(project_root, "project_root")
        self._script_dir = (_directory(script_dir, "script_dir")
                            if script_dir is not None else self._project_root)
        if not self._script_dir.is_relative_to(self._project_root):
            raise ValueError("script_dir must remain inside the selected project")
        self._image_root = _contained(self._project_root / "images", self._project_root)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def script_dir(self) -> Path:
        return self._script_dir

    @property
    def image_root(self) -> Path:
        return self._image_root

    @property
    def roots(self) -> tuple[Path, ...]:
        """Ordered canonical lookup roots, with duplicates removed."""
        return tuple(dict.fromkeys((self.image_root, self.script_dir, self.project_root)))

    def resolve(self, reference: str | Path) -> Path:
        if not isinstance(reference, (str, Path)):
            raise ValueError("Image reference must be a local path string or Path")
        raw = str(reference)
        if not raw.strip() or "\x00" in raw or len(raw) > MAX_REFERENCE_CHARS:
            raise ValueError("Image reference is empty, invalid or too long")
        # Native Windows absolute paths are supported on Windows; a drive-like
        # URL is never interpreted as a relative POSIX asset filename.
        native = Path(raw)
        if _URI_SCHEME.match(raw) and not (native.drive and native.is_absolute()):
            raise ValueError("Image references must be local project files, not URLs")
        path = Path(raw.replace("\\", "/"))
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError("Image reference must be PNG, JPEG, BMP or WebP")
        if any(":" in part for part in path.parts if part != path.anchor):
            raise ValueError("Image reference contains an unsupported path component")
        if path.is_absolute():
            candidates = (path,)
        elif path.parts[0] == "images":
            candidates = (self.project_root / path,)
        elif ".." in path.parts:
            candidates = (self.script_dir / path,)
        elif len(path.parts) == 1:
            candidates = (self.image_root / path, self.script_dir / path, self.project_root / path)
        else:
            candidates = (self.script_dir / path, self.image_root / path, self.project_root / path)

        visited: set[Path] = set()
        for candidate in candidates:
            canonical = _contained(candidate, self.project_root)
            if canonical in visited:
                continue
            visited.add(canonical)
            try:
                metadata = canonical.stat()
            except FileNotFoundError:
                continue
            except OSError as error:
                if error.errno in (errno.ENAMETOOLONG, errno.ELOOP):
                    raise ValueError("Image reference is too long or contains a symlink loop") from error
                raise
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("Image asset must be a regular file")
            if metadata.st_size > MAX_ASSET_BYTES:
                raise ValueError("Image asset exceeds the 16 MiB limit")
            return canonical
        raise FileNotFoundError(f"Image asset was not found in the selected project: {raw}")


def discover_project(script_path: str | Path) -> Path:
    """Find a script's nearest project manifest without reading/executing it.

    The filename may not exist yet. Otherwise use the parent of an ancestor
    named ``scripts`` (the conventional layout), then the script directory.
    Explicit project selection should take precedence over this convenience.
    """
    if not isinstance(script_path, (str, Path)) or not str(script_path) or "\x00" in str(script_path):
        raise ValueError("script_path must be a local script path")
    try:
        path = Path(script_path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("script_path cannot be resolved") from error
    directory = path.parent
    ancestors = (directory, *directory.parents)
    for ancestor in ancestors:
        if (ancestor / "project.json").is_file():
            return ancestor
    for ancestor in ancestors:
        if ancestor.name.casefold() == "scripts":
            return ancestor.parent
    return directory
