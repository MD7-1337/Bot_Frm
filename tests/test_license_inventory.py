"""Artifact provenance rejects mismatched native code and escaping aliases."""
import hashlib
import importlib.util
import json
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
