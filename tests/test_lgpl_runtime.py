"""License guards, integrity and native build command contracts."""
import importlib.util
from pathlib import Path
import tarfile
import io

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lgpl_runtime", ROOT / "tools/build_lgpl_runtime.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_lgpl_guard_rejects_gpl_nonfree_and_unknown_native_binaries():
    builder.require_lgpl("LGPL version 2.1 or later", "--disable-gpl --disable-nonfree")
    for text in ("GPL version 3 or later", "", "commercial", "not LGPL version"):
        with pytest.raises(ValueError):
            builder.require_lgpl(text, "--disable-gpl")
    for flag in ("--enable-gpl", "--enable-nonfree", "--enable-version3", "--enable-libx264", "--enable-libx265"):
        with pytest.raises(ValueError):
            builder.require_lgpl("LGPL version 2.1 or later", flag)


def test_minimal_decoder_configuration_does_not_autodetect_external_libraries(tmp_path):
    commands = builder.build_commands(tmp_path / "prefix", windows=False)
    assert "--disable-autodetect" in commands
    assert "--disable-gpl" in commands and "--disable-nonfree" in commands
    assert "--enable-decoder=h264,mjpeg,rawvideo" in commands
    assert not any(value.startswith("--enable-lib") for value in commands)
    windows = builder.build_commands(tmp_path / "prefix", windows=True)
    assert "--toolchain=msvc" in windows and "--target-os=win64" in windows


def test_source_cache_is_checked_before_accepting_existing_download(tmp_path, monkeypatch):
    path = tmp_path / "source.tar.gz"
    path.write_bytes(b"untrusted old source")
    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"wrong source"))
    with pytest.raises(ValueError, match="integrity"):
        builder.download_verified("https://example.invalid/source", path, "0" * 64)
    assert path.read_bytes() == b"untrusted old source"


def test_source_tar_cannot_escape_extraction_root(tmp_path):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        item = tarfile.TarInfo("../escape")
        item.size = 1
        output.addfile(item, io.BytesIO(b"x"))
    with pytest.raises(tarfile.FilterError):
        builder.extract_source(archive, tmp_path / "extract")
    assert not (tmp_path / "escape").exists()


def test_h264_fixture_is_bounded_and_matches_recorded_digest():
    import base64
    import hashlib
    data = base64.b64decode(builder.H264_FIXTURE)
    assert len(data) == 58
    assert hashlib.sha256(data).hexdigest() == builder.H264_SHA256


def test_windows_import_libraries_use_genuine_msvc_layout_without_changing_dlls(tmp_path):
    native = tmp_path / "bin"
    native.mkdir()
    for name in ("avformat", "avcodec", "avdevice", "avutil", "avfilter", "swscale", "swresample"):
        (native / (name + ".lib")).write_bytes((name + " import library").encode())
        (native / (name + "-61.dll")).write_bytes((name + " native DLL").encode())
    builder.prepare_windows_import_libraries(tmp_path)
    assert (tmp_path / "lib/avcodec.lib").read_bytes() == b"avcodec import library"
    assert (native / "avcodec-61.dll").read_bytes() == b"avcodec native DLL"
    (tmp_path / "lib/avcodec.lib").write_bytes(b"unexpected other toolchain")
    with pytest.raises(RuntimeError, match="overwrite"):
        builder.prepare_windows_import_libraries(tmp_path)
