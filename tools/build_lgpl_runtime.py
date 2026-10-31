"""Build decoder-only LGPL FFmpeg and a genuinely rebuilt PyAV wheel.

Run with Python 3.12 and uv on a native build host. Linux needs a C compiler,
make and pkg-config. Windows additionally needs an initialized VS x64 developer
environment and MSYS2 bash/make. The Windows path requires native CI validation.
The existing application environment and original archives are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

FFMPEG_URL = "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n7.1"
FFMPEG_SHA256 = "7ddad2d992bd250a6c56053c26029f7e728bebf0f37f80cf3f8a0e6ec706431a"
PYAV_URL = "https://files.pythonhosted.org/packages/f8/b6/83129e0337376214b0304893cbf0ad0a54718bb47845517fa5870439ca0b/av-14.2.0.tar.gz"
PYAV_SHA256 = "132b5d52ca262b97b0356e8f48cbbe54d0ac232107a722ab8cc8c0c19eafa17b"
CONFIGURE_OPTIONS = [
    "--disable-gpl", "--disable-nonfree", "--disable-version3",
    "--disable-autodetect", "--disable-static", "--enable-shared",
    "--disable-programs", "--disable-doc", "--disable-debug", "--disable-x86asm",
    "--disable-network", "--disable-everything", "--enable-avcodec",
    "--enable-avformat", "--enable-avfilter", "--enable-avdevice",
    "--enable-swscale", "--enable-swresample",
    "--enable-decoder=h264,mjpeg,rawvideo", "--enable-parser=h264",
    "--enable-demuxer=h264,image2", "--enable-protocol=file,pipe",
    "--enable-filter=buffer,buffersink,scale",
]
# Procedurally generated 32x24 red frame; optional encoder SEI text removed.
H264_FIXTURE = "AAAAAWdCwAraJflhAAADAAEAAAMAPI8SJqAAAAABaM4PyAAAAWWIhDoRigACGPHAAED2OAAIeUnXXg=="
H264_SHA256 = "a52ea0e8dcca0ee6b5cd6d8c1fdd82e2799920c0c9f5bb2405d15f34fba702d0"


def download_verified(url: str, path: Path, digest: str) -> None:
    if path.is_symlink():
        raise ValueError("Build downloads must not be symbolic links")
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return
    with urllib.request.urlopen(url, timeout=90) as response:
        data = response.read(32_000_001)
    if len(data) > 32_000_000 or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Source download integrity/size check failed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def extract_source(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(path, "r:gz") as archive:
        if sum(member.size for member in archive.getmembers()) > 256_000_000:
            raise ValueError("Source archive exceeds extraction limit")
        archive.extractall(destination, filter="data")


def require_lgpl(license_text: str, configuration: str) -> None:
    if not isinstance(license_text, str) or not license_text.startswith("LGPL version"):
        raise ValueError("FFmpeg is not an identified LGPL build")
    forbidden = ("--enable-gpl", "--enable-nonfree", "--enable-version3", "--enable-libx264", "--enable-libx265")
    if any(option in configuration.split() for option in forbidden):
        raise ValueError("FFmpeg enables an excluded license/configuration option")


def build_commands(prefix: Path, *, windows: bool) -> list[str]:
    flags = ["./configure", "--prefix=" + str(prefix).replace("\\", "/"), *CONFIGURE_OPTIONS]
    if windows:
        flags.extend(["--toolchain=msvc", "--arch=x86_64", "--target-os=win64"])
    return flags


def prepare_windows_import_libraries(prefix: Path) -> None:
    # FFmpeg's MSVC install puts .lib files beside the DLLs in bin, while
    # PyAV --ffmpeg-dir searches lib. Copy genuine import libraries only.
    library_dir = prefix / "lib"
    library_dir.mkdir(exist_ok=True)
    for name in ("avformat", "avcodec", "avdevice", "avutil", "avfilter", "swscale", "swresample"):
        source = prefix / "bin" / (name + ".lib")
        if not source.is_file() or not list((prefix / "bin").glob(name + "-*.dll")):
            raise RuntimeError("Native MSVC FFmpeg DLL/import-library pair is missing: " + name)
        destination = library_dir / source.name
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise RuntimeError("Refusing to overwrite a different FFmpeg import library: " + name)
        if not destination.exists():
            shutil.copyfile(source, destination)


def runtime_probe(python: Path, prefix: Path, env: dict) -> dict:
    # This imports the installed repaired wheel, not the original GPL wheel.
    # A build-only search path must not make an incompletely repaired wheel pass.
    probe_env = env.copy()
    probe_env.pop("LD_LIBRARY_PATH", None)
    code = r'''
import av,base64,ctypes,hashlib,json,pathlib,sys
site=pathlib.Path(av.__file__).resolve().parent.parent
files=list((site/'av.libs').glob('*avcodec*'))+list((site/'av').glob('*avcodec*'))
if not files: raise RuntimeError('Repaired wheel has no bundled avcodec library')
codec=ctypes.CDLL(str(files[0]));codec.avcodec_license.restype=ctypes.c_char_p
codec.avcodec_configuration.restype=ctypes.c_char_p
license=codec.avcodec_license().decode();configuration=codec.avcodec_configuration().decode()
utilfiles=list((site/'av.libs').glob('*avutil*'))+list((site/'av').glob('*avutil*'))
if not utilfiles:raise RuntimeError('Repaired wheel has no bundled avutil library')
util=ctypes.CDLL(str(utilfiles[0]));util.av_version_info.restype=ctypes.c_char_p
ffmpeg_version=util.av_version_info().decode()
data=base64.b64decode(sys.argv[1]);assert hashlib.sha256(data).hexdigest()==sys.argv[2]
decoder=av.CodecContext.create('h264','r');frames=[]
for packet in list(decoder.parse(data))+list(decoder.parse(b'')):frames.extend(decoder.decode(packet))
frames.extend(decoder.decode(None));assert len(frames)==1
frame=frames[0];assert (frame.width,frame.height)==(32,24)
pixel=frame.to_ndarray(format='rgb24')[10,10].tolist()
assert pixel[0]>240 and pixel[1]<15 and pixel[2]<15
print(json.dumps(dict(pyav=av.__version__,ffmpeg_version=ffmpeg_version,library=str(files[0]),license=license,configuration=configuration,
 library_versions=av.library_versions,decoded_h264=True,frame_size=[frame.width,frame.height],pixel=pixel)))
'''
    completed = subprocess.run([str(python), "-I", "-c", code, H264_FIXTURE, H264_SHA256],
                               env=probe_env, capture_output=True, text=True, timeout=30, check=True)
    report = json.loads(completed.stdout)
    require_lgpl(report["license"], report["configuration"])
    if (report["pyav"] != "14.2.0" or report["ffmpeg_version"] != "7.1"
            or report["library_versions"]["libavcodec"][0] != 61):
        raise ValueError("Runtime versions differ from the intended PyAV/FFmpeg ABI")
    return report


def main() -> int:
    build_script = Path(__file__).read_bytes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New empty user-owned build directory")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--bash", default="bash", help="MSYS2 bash, only for native Windows")
    parser.add_argument("--existing-prefix", type=Path, help="Reuse a separately built prefix; supply its provenance before distribution")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Use Python 3.12")
    if not 1 <= args.jobs <= 16 or platform.machine().lower() not in ("x86_64", "amd64"):
        parser.error("Use x86-64 and 1..16 jobs")
    windows = sys.platform == "win32"
    if not windows and not sys.platform.startswith("linux"):
        parser.error("Only native Linux/Windows builders are supported")
    output = args.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Choose a new empty output directory; existing data is never cleaned")
    output.mkdir(parents=True, exist_ok=True)
    if shutil.which("uv") is None:
        parser.error("Install the documented uv build tool")
    downloads = output / "downloads"
    ffmpeg_archive, pyav_archive = downloads / "ffmpeg-n7.1.tar.gz", downloads / "av-14.2.0.tar.gz"
    download_verified(FFMPEG_URL, ffmpeg_archive, FFMPEG_SHA256)
    download_verified(PYAV_URL, pyav_archive, PYAV_SHA256)
    source_root = output / "sources"
    extract_source(ffmpeg_archive, source_root / "ffmpeg")
    extract_source(pyav_archive, source_root / "pyav")
    ffmpeg_source, pyav_source = source_root / "ffmpeg/FFmpeg-n7.1", source_root / "pyav/av-14.2.0"
    prefix = args.existing_prefix.resolve() if args.existing_prefix else output / "prefix"
    configure = build_commands(prefix, windows=windows)
    env = os.environ.copy()
    if args.existing_prefix is None:
        if windows:
            cl = shutil.which("cl.exe")
            if cl is None or shutil.which(args.bash) is None:
                parser.error("Initialize VS x64 developer environment and install MSYS2 bash/make")
            # Keep the VS linker ahead of the MSYS hardlink utility. Conversion
            # is performed by MSYS itself; no global path-conversion override.
            # Absolute MSYS paths ensure this shell's make/cygpath are used,
            # even when Git Bash is also installed on the Windows runner.
            prelude = 'msvc_bin=$(/usr/bin/cygpath -u "$1"); shift; export PATH="$msvc_bin:/usr/bin:$PATH"; exec "$@"'
            subprocess.run([args.bash, "--noprofile", "--norc", "-c", prelude,
                            "studio-configure", str(Path(cl).parent), *configure],
                           cwd=ffmpeg_source, env=env, check=True)
            make = [args.bash, "--noprofile", "--norc", "-c",
                    'msvc_bin=$(/usr/bin/cygpath -u "$1"); shift; export PATH="$msvc_bin:/usr/bin:$PATH"; exec /usr/bin/make "$@"',
                    "studio-make", str(Path(cl).parent)]
        else:
            subprocess.run(configure, cwd=ffmpeg_source, env=env, check=True)
            make = ["make"]
        subprocess.run([*make, f"-j{args.jobs}"], cwd=ffmpeg_source, env=env, check=True)
        subprocess.run([*make, "install"], cwd=ffmpeg_source, env=env, check=True)
    if windows:
        prepare_windows_import_libraries(prefix)
    env["PKG_CONFIG_PATH"] = str(prefix / "lib/pkgconfig") + os.pathsep + env.get("PKG_CONFIG_PATH", "")
    if not windows:
        env["LD_LIBRARY_PATH"] = str(prefix / "lib") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        # Standalone Python may record clang even when the host supplies GCC.
        # Preserve explicit compiler choices, otherwise select an installed one.
        env.setdefault("CC", shutil.which("cc") or "gcc")
        env.setdefault("CXX", shutil.which("c++") or "g++")
        env.setdefault("LDSHARED", env["CC"] + " -shared")
    subprocess.run(["uv", "venv", "--python", sys.executable, str(output / "python")], env=env, check=True)
    python = output / ("python/Scripts/python.exe" if windows else "python/bin/python")
    repair = ["delvewheel==1.13.2"] if windows else ["auditwheel==6.8.2", "patchelf==0.19.1.0"]
    subprocess.run(["uv", "pip", "install", "--python", str(python), "Cython==3.0.12",
                    "setuptools==78.1.0", "wheel==0.45.1", "numpy==2.2.4", *repair], env=env, check=True)
    command = [str(python), "setup.py", "bdist_wheel"]
    if windows:
        command.append("--ffmpeg-dir=" + str(prefix))
    subprocess.run(command, cwd=pyav_source, env=env, check=True)
    wheel = next((pyav_source / "dist").glob("*.whl"))
    wheelhouse = output / "wheelhouse"
    wheelhouse.mkdir()
    if windows:
        command = [str(python), "-m", "delvewheel", "repair", "--add-path", str(prefix / "bin"), "-w", str(wheelhouse), str(wheel)]
    else:
        # uv-installed patchelf is in this environment's bin directory.
        env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
        command = [str(python), "-m", "auditwheel", "repair", "-w", str(wheelhouse), str(wheel)]
    subprocess.run(command, env=env, check=True)
    repaired = next(wheelhouse.glob("*.whl"))
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(repaired)], env=env, check=True)
    probe = runtime_probe(python, prefix, env)
    notices = output / "FFmpeg-notices"
    notices.mkdir()
    for name in ("COPYING.LGPLv2.1", "COPYING.LGPLv3", "LICENSE.md"):
        shutil.copyfile(ffmpeg_source / name, notices / name)
    shutil.copyfile(ffmpeg_archive, notices / "ffmpeg-n7.1-source.tar.gz")
    shutil.copyfile(pyav_archive, notices / "pyav-14.2.0-source.tar.gz")
    shutil.copyfile(pyav_source / "LICENSE.txt", notices / "PyAV-LICENSE.txt")
    (notices / Path(__file__).name).write_bytes(build_script)
    provenance = {"ffmpeg_url": FFMPEG_URL, "ffmpeg_sha256": FFMPEG_SHA256,
                  "pyav_url": PYAV_URL, "pyav_sha256": PYAV_SHA256,
                  "configure": configure, "external_prefix": args.existing_prefix is not None,
                  "source_provenance_complete": args.existing_prefix is None,
                  "build_script": str(Path(__file__).name),
                  "build_script_sha256": hashlib.sha256(build_script).hexdigest(), "runtime": probe,
                  "scope": "LGPL runtime inputs; complete Qt/Python/application redistribution review remains separate"}
    (notices / "SOURCE_INFORMATION.json").write_text(json.dumps(provenance, indent=2) + "\n")
    manifest = {**provenance, "platform": platform.platform(), "glibc": platform.libc_ver(),
                "wheel": str(repaired), "wheel_sha256": hashlib.sha256(repaired.read_bytes()).hexdigest(),
                "runtime_python": str(python), "prefix": str(prefix), "notices": str(notices)}
    (output / "lgpl-runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
