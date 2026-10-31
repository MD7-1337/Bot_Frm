from pathlib import Path
import hashlib
import os
import tarfile

import pytest

from tools.build_linux import create_portable_archive, extract_generated_archive, source_digest


def test_linux_archive_preserves_executable_and_checksum_after_relocation(tmp_path):
    payload = tmp_path / "Application With Spaces"
    payload.mkdir()
    binary = payload / "AndroidAutomationStudio"
    binary.write_bytes(b"trusted generated fixture")
    binary.chmod(0o755)
    archive = tmp_path / "portable.tar.gz"
    checksum = create_portable_archive(payload, archive)
    assert checksum == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_suffix(".gz.sha256").read_text() == f"{checksum}  portable.tar.gz\n"
    relocated = tmp_path / "Relocated Path"
    relocated.mkdir()
    extract_generated_archive(archive, relocated)
    restored = relocated / payload.name / binary.name
    assert restored.read_bytes() == binary.read_bytes()
    if os.name == "posix":
        assert restored.stat().st_mode & 0o111
    with pytest.raises(FileExistsError):
        create_portable_archive(payload, archive)


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="Links unavailable")
def test_linux_archive_accepts_only_internal_binary_aliases(tmp_path):
    payload = tmp_path / "Application"
    payload.mkdir()
    (payload / "lib-real.so").write_bytes(b"fixture")
    alias = payload / "lib.so"
    try:
        alias.symlink_to("lib-real.so")
    except OSError:
        pytest.skip("Host does not permit symlinks")
    archive = tmp_path / "safe.tar.gz"
    create_portable_archive(payload, archive)
    with tarfile.open(archive) as stream:
        assert stream.getmember("Application/lib.so").issym()
    alias.unlink()
    outside = tmp_path / "external.so"
    outside.write_bytes(b"outside package")
    alias.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        create_portable_archive(payload, tmp_path / "unsafe.tar.gz")


def test_source_digest_tracks_input_contents_not_cache_files(tmp_path):
    (tmp_path / "app").mkdir()
    source = tmp_path / "app/main.py"
    source.write_text("version=1")
    before = source_digest(tmp_path)
    cache = tmp_path / "app/__pycache__"
    cache.mkdir()
    (cache / "main.pyc").write_bytes(b"cache")
    assert source_digest(tmp_path) == before
    source.write_text("version=2")
    assert source_digest(tmp_path) != before
