# LGPL FFmpeg and PyAV runtime

`tools/build_lgpl_runtime.py` builds FFmpeg 7.1 from verified upstream source,
builds PyAV 14.2.0 against those libraries, and repairs the wheel to carry its
own shared libraries. It does not change the application's license. The PyAV
binary wheels previously installed for development can contain GPL FFmpeg;
they are not approved release inputs.

The FFmpeg configuration explicitly disables GPL, nonfree and version-3
components, external-library autodetection, encoders, networking, programs and
assembly. It enables H.264, MJPEG and raw-video decoding plus the libraries and
format conversion needed by PyAV. This supports the application's H.264 stream
decoder without distributing x264 or x265. New codec requirements must be added
deliberately and reviewed before distribution.

## Verified inputs

| Input | Source | SHA-256 |
| --- | --- | --- |
| FFmpeg 7.1 | [Official n7.1 source archive](https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n7.1) | `7ddad2d992bd250a6c56053c26029f7e728bebf0f37f80cf3f8a0e6ec706431a` |
| PyAV 14.2.0 | [PyPI source archive](https://files.pythonhosted.org/packages/f8/b6/83129e0337376214b0304893cbf0ad0a54718bb47845517fa5870439ca0b/av-14.2.0.tar.gz) | `132b5d52ca262b97b0356e8f48cbbe54d0ac232107a722ab8cc8c0c19eafa17b` |

Downloads have size limits and are hashed before extraction. An unexpected
archive fails the build. Python build tools are pinned in the helper. Native
compiler and operating-system versions remain properties of the selected CI
runner; wheel hashes are recorded after each build rather than assumed to be
identical across runners.

## Build on Ubuntu

Use x86-64 Python 3.12, `uv`, a C/C++ compiler, `make`, and `pkg-config`. Build on
the oldest supported Linux baseline: Ubuntu 22.04 for the current release. A
successful build on a newer host does not validate the complete frozen
application on Ubuntu 22.04.

```sh
python tools/build_lgpl_runtime.py --output build/lgpl-runtime
```

The output directory must be empty or absent. The helper builds in its own
virtual environment and never installs into the application's environment.
It uses `auditwheel` to bundle the freshly built FFmpeg shared libraries.

## Build on Windows

Use an actual x64 Windows runner, Python 3.12 and `uv`. Initialize the Visual
Studio x64 developer environment before invoking the helper; `cl.exe` and the
MSVC linker must be available. Install MSYS2's `make` and use its `bash.exe`.
For GitHub Actions, `ilammy/msvc-dev-cmd` with `arch: x64` and
`msys2/setup-msys2` with `msystem: MSYS`, `path-type: inherit`, and `install: make`
provide the required environments. Workflow action revisions should follow the
repository's pinning policy.

```powershell
python tools/build_lgpl_runtime.py --output build/lgpl-runtime `
  --bash C:/msys64/usr/bin/bash.exe
```

FFmpeg is compiled with its native MSVC toolchain. The helper keeps the Visual
Studio linker ahead of MSYS's unrelated `link.exe`. PyAV uses FFmpeg's matching
headers and import libraries through its `--ffmpeg-dir` option. `delvewheel`
then bundles the resulting DLLs and adds Python DLL-loading support. DLLs from
the original GPL wheel are never reused or renamed into this build.

FFmpeg's MSVC install places genuine `.lib` import libraries in `prefix/bin`.
The helper checks that all seven DLL/import-library pairs exist, then copies
those import libraries into `prefix/lib`, where PyAV expects them. It refuses
to overwrite a different existing import library. Use a build directory without
spaces, as required by parts of the upstream FFmpeg build system.

Native Windows CI must pass the runtime probe and frozen-application tests before
the resulting ZIP or installer can be described as tested. Linux validation is
not Windows validation.

## Use the result for packaging

Run source tests that generate encoded video fixtures before replacing the
development wheel: the minimal release runtime intentionally has no encoders.
After building, load `wheel` from `build/lgpl-runtime/lgpl-runtime.json` and install
that exact repaired wheel into the application's packaging environment:

```sh
uv pip install --python .venv/bin/python --reinstall /absolute/path/to/repaired-av.whl
export STUDIO_LGPL_RUNTIME_DIR="$PWD/build/lgpl-runtime"
```

On Windows, use `.venv/Scripts/python.exe` and set the same environment variable
in PowerShell. Then run the normal platform build and the distribution audit.
The notice collector reads the manifest and copies `FFmpeg-notices` into the
frozen application's `THIRD_PARTY_NOTICES/FFmpeg` directory. Keep this source and
notice directory alongside all redistributed binaries, including installer
payloads. The project's separate Qt, Python and remaining dependency notices
must also pass the distribution review.

Each successful helper run:

* Checks the **actual repaired wheel's** `avcodec_license()`,
  `avcodec_configuration()` and `av_version_info()` values.
* Requires LGPL, FFmpeg 7.1, PyAV 14.2.0, and the expected avcodec ABI; rejects
  GPL, nonfree, version-3, x264 and x265 enable flags.
* Decodes a known 58-byte H.264 fixture and checks its frame dimensions and RGB
  pixel. The Linux probe removes the build-only library search path so a broken
  repair cannot pass by finding the original prefix.
* Records wheel SHA-256, runtime evidence, configuration and source provenance
  in `lgpl-runtime.json` and `FFmpeg-notices/SOURCE_INFORMATION.json`.
* Copies the exact verified FFmpeg source archive, LGPL 2.1 and LGPL 3 license
  texts, and upstream `LICENSE.md` for the shipped FFmpeg build. It also includes
  the verified PyAV source archive, PyAV's BSD license and this build helper;
  the helper's SHA-256 is recorded in the provenance.

`--existing-prefix` is a development diagnostic. Its manifest deliberately sets
`source_provenance_complete` to `false`; release auditing must reject that output
because the helper did not build that prefix itself. Normal builds set it to
`true` only after building the verified source and passing the runtime probe.

Keep the original 306 MiB Ubuntu archive unchanged. A rebuilt LGPL-compatible
archive is a separate artifact and needs its own hash and validation evidence.

## Evidence and limits

The initial native Linux proof compiled all seven FFmpeg libraries and rebuilt
and repaired PyAV. The installed repaired wheel reported FFmpeg 7.1,
`LGPL version 2.1 or later`, avcodec 61.19.100, and decoded the 32-by-24 H.264
fixture to a red pixel `[252, 0, 0]` without the build-prefix library search path.
The wheel was tagged `manylinux_2_35_x86_64` by `auditwheel`; the host itself used
glibc 2.41. This establishes the decoder build path, not full Ubuntu application,
Windows, or physical Android validation. CI logs and manifests for the final
commit are the authoritative evidence for published artifacts.
