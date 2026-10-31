"""Validate local Monaco against hashes of the pinned, verified npm archive.

The manifest is source-controlled; it is never accepted from the vendor folder.
Validation does not execute JavaScript and rejects symlinked vendor resources.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from app.resources import resource_root

VERSION = "0.52.2"
REPAIR = "Run this checkout's Python: python tools/fetch_monaco.py (no symlinks required)."
PACKAGED_REPAIR = "Re-extract or reinstall the complete official application package into a user-owned folder. Keep its bundled editor resources together; no Python installation or symbolic links are required."


def repair_guidance():
    return PACKAGED_REPAIR if getattr(sys, 'frozen', False) else REPAIR


class MonacoAssetsError(ValueError):
    pass


def validate_monaco(editor_root: Path | None = None, *, manifest: dict | None = None) -> dict:
    """Check every pinned file, returning version/count; raise an actionable error."""
    editor_root = Path(editor_root) if editor_root is not None else resource_root() / "editor_web"
    repair = repair_guidance()
    if manifest is None:
        try:
            manifest = json.loads(Path(__file__).with_name("assets_manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise MonacoAssetsError('Pinned Monaco manifest is unavailable or corrupt. ' + repair) from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get('version'), str) or not isinstance(manifest.get('files'), dict):
        raise MonacoAssetsError('Invalid pinned Monaco asset manifest. ' + repair)
    vendor = editor_root / "vendor"
    try:
        if vendor.is_symlink() or editor_root.is_symlink():
            raise MonacoAssetsError("Monaco asset directory is a symbolic link. " + repair)
        if not vendor.is_dir():
            raise MonacoAssetsError("Monaco assets missing at " + str(vendor) + ". " + repair)
        for relative, expected in manifest["files"].items():
            parts = Path(relative).parts
            if not parts or ".." in parts or Path(relative).is_absolute():
                raise MonacoAssetsError("Invalid pinned Monaco asset manifest. " + repair)
            if (not isinstance(expected, dict) or type(expected.get('size')) is not int
                    or expected['size'] < 0 or not isinstance(expected.get('sha256'), str)):
                raise MonacoAssetsError("Invalid pinned Monaco asset manifest. " + repair)
            path = vendor / relative
            if any((vendor / Path(*parts[:index])).is_symlink() for index in range(1, len(parts) + 1)):
                raise MonacoAssetsError("Monaco asset is a symbolic link: " + relative + ". " + repair)
            if not path.is_file():
                raise MonacoAssetsError("Monaco asset missing: " + relative + ". " + repair)
            if path.stat().st_size != expected["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
                raise MonacoAssetsError("Monaco asset corrupt or wrong version: " + relative + ". " + repair)
    except (OSError, RuntimeError) as error:
        raise MonacoAssetsError("Cannot read local Monaco assets: " + str(error) + ". " + repair) from error
    return {"version": manifest["version"], "files_verified": len(manifest["files"])}
