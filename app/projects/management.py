"""Versioned, inert project metadata and bounded portable project archives.

Projects contain trusted Python *data*. Opening, searching, importing or restoring
one never imports a module, runs a script, enables a task or adopts device trust.
The path checks protect normal filesystem use, not hostile concurrent mutation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from uuid import uuid4
import zipfile

SCHEMA_VERSION = 2
MANIFEST = "project.json"
DIRECTORIES = ("scripts", "images", "recordings", "tasks", "settings", "run_configurations")
MAX_MANIFEST_BYTES = 1_000_000
MAX_FILES = 2_000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_PROJECT_BYTES = 256 * 1024 * 1024
_PRIVATE = {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
_FORBIDDEN = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
             *(f"COM{i}" for i in "123456789¹²³"), *(f"LPT{i}" for i in "123456789¹²³")}


class ProjectError(ValueError):
    """Invalid, unsupported or unsafe project data."""


class ProjectConflictError(ProjectError):
    """The manifest changed on disk after it was opened."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _name(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or "\x00" in value:
        raise ProjectError("Project name must contain 1–120 characters")
    return value.strip()


def _safe_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ProjectError("Project paths must be relative portable paths")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or value != path.as_posix() or any(
        part in (".", "..", "") or _FORBIDDEN.search(part) or part.endswith((".", " "))
        or len(part) > 255 or part.split(".", 1)[0].rstrip(" .").upper() in _RESERVED for part in path.parts
    ):
        raise ProjectError("Unsafe or nonportable project path")
    return path


def _json(data: dict) -> bytes:
    try:
        payload = (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ProjectError("Project metadata must be finite JSON data") from error
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ProjectError("Project metadata exceeds 1 MB")
    return payload


def _decode(payload: bytes) -> dict:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ProjectError("Project metadata exceeds 1 MB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProjectError("Duplicate project metadata key")
            result[key] = value
        return result
    try:
        value = json.loads(payload, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ProjectError("Nonfinite project number")))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ProjectError(f"Invalid project metadata: {error}") from error
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
        raise ProjectError("Project metadata needs an integer schema_version")
    return value


def _validate(data: dict) -> dict:
    data = deepcopy(data)
    if type(data.get("schema_version")) is not int or data.get("schema_version") != SCHEMA_VERSION:
        raise ProjectError(f"Unsupported project schema; expected {SCHEMA_VERSION}")
    data["name"] = _name(data.get("name"))
    if not isinstance(data.get("id"), str) or not re.fullmatch(r"[a-f0-9]{32}", data["id"]):
        raise ProjectError("Invalid project identifier")
    for key in ("created_at", "updated_at"):
        try:
            stamp = datetime.fromisoformat(data[key])
            if stamp.utcoffset() is None:
                raise ValueError("timezone missing")
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectError(f"Project {key} must be timezone aware") from error
    if type(data.get("autosave", False)) is not bool:
        raise ProjectError("Project autosave must be a boolean")
    if not isinstance(data.get("recognition", {}), dict):
        raise ProjectError("Project recognition settings must be an object")
    for key in ("run_configurations", "task_definitions", "workflow_definitions"):
        if not isinstance(data.get(key, []), list):
            raise ProjectError(f"Project {key} must be a list")
    _json(data)
    return data


def validate_configuration(recognition, runs):
    """Validate the explicitly supported recognition and script-open presets."""
    if not isinstance(recognition, dict) or set(recognition) - {"threshold", "scales", "preprocessing", "region"}:
        raise ProjectError("Recognition supports threshold, scales, preprocessing and optional region")
    threshold = recognition.get("threshold", .85)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ProjectError("Recognition threshold must be finite and between 0 and 1")
    scales = recognition.get("scales", [1.0])
    if not isinstance(scales, list) or not 1 <= len(scales) <= 16 or any(isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) or not .1 <= s <= 4 for s in scales):
        raise ProjectError("Recognition scales require 1–16 finite values from 0.1 to 4")
    if recognition.get("preprocessing", "none") not in ("none", "grayscale", "threshold", "edges"):
        raise ProjectError("Unsupported recognition preprocessing")
    region = recognition.get("region")
    if region is not None and (not isinstance(region, list) or len(region) != 4 or any(type(n) is not int for n in region) or any(n < 0 for n in region[:2]) or any(n <= 0 for n in region[2:])):
        raise ProjectError("Recognition region must be [x, y, width, height] with valid positive extent")
    if not isinstance(runs, list) or len(runs) > 100:
        raise ProjectError("At most 100 script run configurations are supported")
    names = set()
    for run in runs:
        if not isinstance(run, dict) or set(run) != {"name", "script"}:
            raise ProjectError("A run configuration contains name and project-relative script")
        name = _name(run["name"])
        if name.casefold() in names:
            raise ProjectError("Run configuration names must be unique")
        names.add(name.casefold())
        path = _safe_path(run["script"])
        if path.suffix.casefold() != ".py":
            raise ProjectError("Run configuration scripts must be Python files")
    return deepcopy(recognition), deepcopy(runs)


def _atomic(path: Path, payload: bytes, *, exclusive=False) -> None:
    if path.is_symlink():
        raise ProjectError("Project files may not be symbolic links")
    descriptor, temporary = tempfile.mkstemp(prefix=".studio-save-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if exclusive:
            # Hard linking the complete temporary file fails if the path exists,
            # unlike a check followed by replace. Windows supports local NTFS links.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass  # Directory fsync is unavailable on Windows.
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_manifest(root: Path) -> bytes:
    path = root / MANIFEST
    if path.is_symlink() or not path.is_file():
        raise ProjectError("Select a project with a regular project.json manifest")
    with path.open("rb") as stream:
        return stream.read(MAX_MANIFEST_BYTES + 1)


def _root(path: Path | str) -> Path:
    raw = Path(path).expanduser()
    if raw.is_symlink():
        raise ProjectError("Project root may not be a symbolic link")
    root = raw.resolve(strict=True)
    if not root.is_dir():
        raise ProjectError("Project root must be a directory")
    for name in DIRECTORIES:
        candidate = root / name
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
            raise ProjectError(f"Project {name} must be a regular directory")
    return root


def _included(path: PurePosixPath) -> bool:
    if any(part.casefold() in _PRIVATE or part.startswith(".") for part in path.parts):
        return False
    if path.suffix.casefold() in {".pem", ".key", ".p12", ".pfx", ".log", ".pyc"}:
        return False
    return path.parts[0] in DIRECTORIES or (len(path.parts) == 1 and (
        path.name == MANIFEST or path.suffix.casefold() in {".py", ".md", ".txt"}))


@dataclass(frozen=True)
class SearchHit:
    path: str
    line: int
    text: str


class ProjectStore:
    """One open metadata snapshot; writes detect an externally changed manifest."""

    def __init__(self, root: Path, metadata: dict, fingerprint: str):
        self.root = root
        self._metadata = metadata
        self._fingerprint = fingerprint

    @property
    def metadata(self) -> dict:
        return deepcopy(self._metadata)

    @classmethod
    def create(cls, root: Path | str, name: str) -> ProjectStore:
        """Create in a new destination; existing directories are never overwritten."""
        name = _name(name)
        target = Path(root).expanduser().absolute()
        if target.exists() or target.is_symlink():
            raise FileExistsError("Choose a new project directory")
        if not target.parent.is_dir():
            raise ProjectError("The parent directory must exist")
        stamp = _utc()
        metadata = {"schema_version": SCHEMA_VERSION, "id": uuid4().hex,
                    "name": name, "created_at": stamp, "updated_at": stamp,
                    "autosave": False, "recognition": {}, "run_configurations": [],
                    "task_definitions": []}
        with tempfile.TemporaryDirectory(prefix=".studio-create-", dir=target.parent) as temporary:
            staging = Path(temporary) / "project"
            staging.mkdir()
            for directory in DIRECTORIES:
                (staging / directory).mkdir()
            _atomic(staging / MANIFEST, _json(metadata))
            # rename fails for a nonempty destination. Recheck avoids ordinary
            # races; hostile concurrent parent mutation is outside this boundary.
            if target.exists() or target.is_symlink():
                raise FileExistsError("Project destination already exists")
            staging.rename(target)
        return cls.open(target)

    @classmethod
    def open(cls, root: Path | str, *, migrate=True) -> ProjectStore:
        root = _root(root)
        payload = _read_manifest(root)
        metadata = _decode(payload)
        if metadata["schema_version"] == 1:
            if not migrate:
                raise ProjectError("Schema 1 project requires an explicit migration")
            stamp = _utc()
            converted = {**metadata, "schema_version": SCHEMA_VERSION,
                         "id": uuid4().hex, "name": _name(metadata.get("name", root.name)),
                         "created_at": stamp, "updated_at": stamp,
                         "autosave": False, "recognition": metadata.get("recognition", {}),
                         "run_configurations": metadata.get("run_configurations", []),
                         "task_definitions": metadata.get("task_definitions", [])}
            metadata = _validate(converted)
            backup = root / f".project-v1-{uuid4().hex}.json"
            _atomic(backup, payload, exclusive=True)
            if _read_manifest(root) != payload:
                raise ProjectConflictError("Manifest changed while preparing migration")
            _atomic(root / MANIFEST, _json(metadata))
            payload = _read_manifest(root)
        metadata = _validate(metadata)
        return cls(root, metadata, hashlib.sha256(payload).hexdigest())

    def save(self, metadata: dict | None = None) -> None:
        data = _validate(metadata if metadata is not None else self._metadata)
        data["updated_at"] = _utc()
        current = _read_manifest(self.root)
        if hashlib.sha256(current).hexdigest() != self._fingerprint:
            raise ProjectConflictError("Project metadata changed on disk; reopen before saving")
        payload = _json(data)
        _atomic(self.root / MANIFEST, payload)
        self._metadata = data
        self._fingerprint = hashlib.sha256(payload).hexdigest()

    def rename(self, name: str) -> None:
        data = self.metadata
        data["name"] = _name(name)
        self.save(data)

    def configure(self, recognition, runs):
        recognition, runs = validate_configuration(recognition, runs)
        data = self.metadata
        data.update(recognition=recognition, run_configurations=runs)
        self.save(data)

    def configured_script(self, name):
        _, runs = validate_configuration(self.metadata.get("recognition", {}), self.metadata.get("run_configurations", []))
        entry = next((item for item in runs if item["name"] == name), None)
        if entry is None:
            raise ProjectError("Choose an existing run configuration")
        path = self.root.joinpath(*_safe_path(entry["script"]).parts).resolve(strict=True)
        if not path.is_relative_to(self.root) or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ProjectError("Configured script must remain a bounded file inside this project")
        return path

    def recognition_code(self, reference):
        from app.projects.library import AssetLibrary
        AssetLibrary(self.root).resolve(reference)
        recognition, _ = validate_configuration(self.metadata.get("recognition", {}), self.metadata.get("run_configurations", []))
        code = "target = Pattern(" + json.dumps(str(reference), ensure_ascii=True) + ")"
        code += f".similar({recognition.get('threshold', .85)!r})"
        code += ".atScales(" + ", ".join(repr(n) for n in recognition.get("scales", [1.0])) + ")"
        code += ".preprocess(" + json.dumps(recognition.get("preprocessing", "none")) + ")"
        if region := recognition.get("region"):
            code += ".inRegion(Region(" + ", ".join(str(n) for n in region) + "))"
        return code + "\n"

    def trash(self, confirmation):
        """Reversible project deletion: move everything into a sibling trash folder."""
        if confirmation != self.metadata["name"]:
            raise ProjectError("Type the exact project display name to move it to trash")
        root = _root(self.root)
        if root == root.parent or root == Path.home().resolve():
            raise ProjectError("This directory cannot be moved to project trash")
        if hashlib.sha256(_read_manifest(root)).hexdigest() != self._fingerprint:
            raise ProjectConflictError("Project metadata changed; reopen before moving it")
        trash = root.parent / ".studio-trash"
        if trash.is_symlink() or (trash.exists() and not trash.is_dir()):
            raise ProjectError("Project trash must be a regular sibling directory")
        trash.mkdir(exist_ok=True)
        destination = trash / (root.name + "-" + uuid4().hex)
        root.rename(destination)
        return destination

    @classmethod
    def recover_manifest(cls, root, backup):
        """Restore validated metadata while preserving the current corrupt bytes."""
        root = _root(root)
        backup = Path(backup).expanduser()
        if backup.is_symlink() or not backup.is_file() or backup.stat().st_size > MAX_MANIFEST_BYTES:
            raise ProjectError("Choose a bounded regular metadata backup")
        data = _decode(backup.read_bytes())
        if data["schema_version"] == 1:
            stamp = _utc()
            data = {**data, "schema_version": SCHEMA_VERSION, "id": uuid4().hex,
                    "name": _name(data.get("name", root.name)), "created_at": stamp,
                    "updated_at": stamp, "autosave": False, "recognition": data.get("recognition", {}),
                    "run_configurations": data.get("run_configurations", []),
                    "task_definitions": data.get("task_definitions", [])}
        data = _validate(data)
        payload = _json(data)
        before = _read_manifest(root)
        _atomic(root / (".project-before-recovery-" + uuid4().hex + ".json"), before, exclusive=True)
        if _read_manifest(root) != before:
            raise ProjectConflictError("Manifest changed during recovery; current bytes were preserved")
        _atomic(root / MANIFEST, payload)
        return cls.open(root)

    def files(self) -> list[tuple[Path, str]]:
        """Collect only portable project content; reject included symlinks."""
        root = _root(self.root)
        output = []
        total = 0
        folded = set()
        for directory, folders, files in os.walk(root, followlinks=False):
            parent = Path(directory)
            folders[:] = sorted(folder for folder in folders if _included(PurePosixPath((parent / folder).relative_to(root).as_posix())))
            for folder in folders:
                if (parent / folder).is_symlink():
                    raise ProjectError("Project archives cannot contain symbolic links")
            for name in sorted(files):
                path = parent / name
                reference = path.relative_to(root).as_posix()
                if not _included(PurePosixPath(reference)):
                    continue
                _safe_path(reference)
                if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
                    raise ProjectError("Project content must contain only regular files")
                size = path.stat().st_size
                total += size
                if size > MAX_FILE_BYTES or total > MAX_PROJECT_BYTES or len(output) >= MAX_FILES:
                    raise ProjectError("Project exceeds archive size or file-count limits")
                key = reference.casefold()
                if key in folded:
                    raise ProjectError("Project paths collide on Windows")
                folded.add(key)
                output.append((path, reference))
        return output

    def export(self, destination: Path | str) -> Path:
        """Write a complete archive atomically, without replacing an existing file."""
        destination = Path(destination).expanduser().absolute()
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Choose a new archive filename")
        if destination.is_relative_to(self.root):
            raise ProjectError("Save project archives outside the project directory")
        _validate(_decode(_read_manifest(self.root)))
        files = self.files()
        descriptor, temporary = tempfile.mkstemp(prefix=".studio-archive-", dir=destination.parent)
        os.close(descriptor)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for source, reference in files:
                    archive.write(source, reference)
            os.link(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return destination

    def backup(self, destination: Path | str) -> Path:
        return self.export(destination)

    @classmethod
    def import_archive(cls, archive_path: Path | str, destination: Path | str) -> ProjectStore:
        """Extract to staging, validate metadata, then promote to a new directory."""
        destination = Path(destination).expanduser().absolute()
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Import destination must be a new directory")
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                members = archive.infolist()
                if len(members) > MAX_FILES:
                    raise ProjectError("Archive has too many entries")
                total = 0
                keys = set()
                checked = []
                for member in members:
                    reference = member.filename.rstrip("/") if member.is_dir() else member.filename
                    path = _safe_path(reference)
                    mode = member.external_attr >> 16
                    kind = stat.S_IFMT(mode)
                    if (member.flag_bits & 1 or kind not in (0, stat.S_IFDIR, stat.S_IFREG)
                            or (member.is_dir() and kind == stat.S_IFREG)
                            or (not member.is_dir() and kind == stat.S_IFDIR)):
                        raise ProjectError("Archive contains encrypted or special files")
                    if not _included(path):
                        raise ProjectError("Archive contains unsupported or private project content")
                    if path.as_posix().casefold() in keys:
                        raise ProjectError("Archive contains duplicate or case-colliding paths")
                    keys.add(path.as_posix().casefold())
                    total += member.file_size
                    if member.file_size > MAX_FILE_BYTES or total > MAX_PROJECT_BYTES:
                        raise ProjectError("Archive exceeds project size limits")
                    checked.append((member, path))
                if MANIFEST not in keys:
                    raise ProjectError("Archive has no project.json")
                with tempfile.TemporaryDirectory(prefix=".studio-import-", dir=destination.parent) as temporary:
                    staging = Path(temporary) / "project"
                    staging.mkdir()
                    for member, path in checked:
                        target = staging.joinpath(*path.parts)
                        if member.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open("xb") as output:
                            remaining = member.file_size
                            while remaining:
                                block = source.read(min(65536, remaining))
                                if not block:
                                    raise ProjectError("Truncated archive member")
                                output.write(block)
                                remaining -= len(block)
                            if source.read(1):
                                raise ProjectError("Archive member exceeds declared size")
                    cls.open(staging)  # Migration/validation occur before destination is exposed.
                    for directory in DIRECTORIES:
                        (staging / directory).mkdir(exist_ok=True)
                    if destination.exists() or destination.is_symlink():
                        raise FileExistsError("Import destination already exists")
                    staging.rename(destination)
        except (zipfile.BadZipFile, RuntimeError, EOFError) as error:
            raise ProjectError(f"Invalid project archive: {error}") from error
        return cls.open(destination)

    restore = import_archive

    def duplicate(self, destination: Path | str) -> ProjectStore:
        destination = Path(destination).expanduser().absolute()
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Duplicate destination must be a new directory")
        with tempfile.TemporaryDirectory(prefix=".studio-duplicate-", dir=destination.parent) as temporary:
            archive = self.export(Path(temporary) / "project.zip")
            result = self.import_archive(archive, Path(temporary) / "copy")
            data = result.metadata
            data.update(id=uuid4().hex, name=self.metadata["name"][:113] + " (copy)", created_at=_utc())
            result.save(data)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError("Duplicate destination already exists")
            result.root.rename(destination)
        return self.open(destination)

    def search(self, query: str, *, limit=200) -> list[SearchHit]:
        if not isinstance(query, str) or not query or len(query) > 1000:
            raise ProjectError("Enter 1–1000 characters to search")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ProjectError("Search limit must be 1–1000")
        output = []
        for path, reference in self.files():
            if path.suffix.casefold() not in {".py", ".json", ".md", ".txt"} or path.stat().st_size > MAX_MANIFEST_BYTES:
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeError:
                continue
            for number, line in enumerate(source.splitlines(), 1):
                if query.casefold() in line.casefold():
                    output.append(SearchHit(reference, number, line[:500]))
                    if len(output) >= limit:
                        return output
        return output

    def missing_assets(self) -> list[str]:
        """Report literal image references in scripts; dynamic Python is not evaluated."""
        import ast
        from app.projects.library import AssetLibrary, IMAGE_EXTENSIONS
        output = set()
        for path, reference in self.files():
            if path.suffix.casefold() != ".py" or path.stat().st_size > MAX_MANIFEST_BYTES:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (UnicodeError, SyntaxError):
                continue
            library = AssetLibrary(self.root, path.parent)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and Path(node.value).suffix.casefold() in IMAGE_EXTENSIONS:
                    try:
                        library.resolve(node.value)
                    except (ValueError, OSError):
                        output.add(f"{reference}:{node.lineno}: {node.value}")
        return sorted(output)
