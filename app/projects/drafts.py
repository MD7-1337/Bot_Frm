"""Bounded, inert recovery copies. Timer saves never replace user script files."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from app.projects.management import _atomic

MAX_DOCUMENTS = 20
MAX_SOURCE = 1_000_000
MAX_SESSION = 42_000_000
MAX_STORAGE = 100_000_000
_IDENTITY = re.compile(r"[a-f0-9]{32}")


def validate_documents(documents):
    if not isinstance(documents, list) or len(documents) > MAX_DOCUMENTS:
        raise ValueError("Recovery supports at most 20 script buffers")
    result, seen = [], set()
    for item in documents:
        if not isinstance(item, dict) or set(item) != {"key", "path", "project", "source", "saved"}:
            raise ValueError("Invalid recovery buffer")
        if not isinstance(item["key"], str) or not _IDENTITY.fullmatch(item["key"]) or item["key"] in seen:
            raise ValueError("Recovery buffer identities must be unique")
        seen.add(item["key"])
        for field in ("source", "saved"):
            if not isinstance(item[field], str) or len(item[field].encode("utf-8")) > MAX_SOURCE:
                raise ValueError("Recovery source exceeds 1 MB")
        for field in ("path", "project"):
            value = item[field]
            if field == "path" and value is None:
                continue
            if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value or not Path(value).is_absolute():
                raise ValueError("Recovery context must use absolute local paths")
        result.append(dict(item))
    return result


class DraftStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()
        if self.root.is_symlink():
            raise ValueError("Recovery directory cannot be a symbolic link")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, identity):
        if not isinstance(identity, str) or not _IDENTITY.fullmatch(identity):
            raise ValueError("Invalid recovery session identity")
        return self.root / (identity + ".json")

    def write(self, identity, documents):
        documents = validate_documents(documents)
        target = self._path(identity)
        if not documents:
            self.remove(identity)
            return
        value = {"schema_version": 1, "session": identity,
                 "updated_at": datetime.now(timezone.utc).isoformat(), "documents": documents}
        payload = json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8")
        if len(payload) > MAX_SESSION:
            raise ValueError("Recovery snapshot exceeds size limit")
        total = sum(p.stat().st_size for p in self.root.glob("*.json") if p != target and p.is_file() and not p.is_symlink())
        if total + len(payload) > MAX_STORAGE:
            raise ValueError("Recovery storage is full; review old snapshots. No recovery data was deleted.")
        _atomic(target, payload)
        if os.name == "posix":
            target.chmod(0o600)

    def read(self, identity):
        path = self._path(identity)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SESSION:
            raise ValueError("Recovery snapshot is not a bounded regular file")
        with path.open("rb") as stream:
            payload = stream.read(MAX_SESSION + 1)
        if len(payload) > MAX_SESSION:
            raise ValueError("Recovery snapshot exceeds size limit")
        value = json.loads(payload)
        if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
                or value["schema_version"] != 1 or value.get("session") != identity):
            raise ValueError("Unsupported recovery snapshot")
        stamp = datetime.fromisoformat(value["updated_at"])
        if stamp.utcoffset() is None:
            raise ValueError("Recovery timestamp must have a timezone")
        value["documents"] = validate_documents(value.get("documents"))
        return value

    def sessions(self, *, exclude=None):
        result, problems = [], []
        for path in sorted(self.root.glob("*.json"))[:100]:
            if path.stem == exclude:
                continue
            try:
                result.append(self.read(path.stem))
            except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
                problems.append(f"{path.name}: {error}")
        return result, problems

    def remove(self, identity):
        path = self._path(identity)
        if path.is_symlink():
            raise ValueError("Recovery snapshots cannot be symbolic links")
        path.unlink(missing_ok=True)

    def discard_documents(self, identity, keys, *, expected_updated_at):
        """Explicit removal refuses to delete a newer snapshot from another instance."""
        if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
            raise ValueError("Invalid selected recovery buffers")
        current = self.read(identity)
        if current["updated_at"] != expected_updated_at:
            raise ValueError("Recovery snapshot changed; reopen and review the current copy")
        selected = set(keys)
        if selected - {item["key"] for item in current["documents"]}:
            raise ValueError("Selected recovery buffers are no longer available")
        self.write(identity, [item for item in current["documents"] if item["key"] not in selected])


def snapshot_fingerprint(documents):
    return hashlib.sha256(json.dumps(documents, ensure_ascii=True, sort_keys=True).encode()).hexdigest()
