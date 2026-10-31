# Release notice and license review

This repository does not currently supply an application LICENSE file. Establish
the project's distribution license before making a public binary release. Build
outputs are developer review artifacts, not a claim of distribution clearance.

`tools/build_windows.py` copies installed distribution license/notice files and
records package versions under `build/release-notices/`. PyInstaller also collects
the package metadata. That inventory must be compared with the **actual** bundled
DLLs/resources, not accepted as an exhaustive bill of materials.

| Component | Release obligations to verify |
| --- | --- |
| Python 3.12 | PSF license and bundled runtime notices |
| PySide6 6.8.3 / Shiboken / Qt | Applicable LGPLv3/GPL/commercial path, notices, corresponding source/relinking information for selected modules |
| QtWebEngine / Chromium | Full third-party notices for exact deployed QtWebEngine binary and codec build |
| Monaco 0.52.2 | MIT license and ThirdPartyNotices.txt from the verified npm archive |
| NumPy 2.2.4 | BSD-style license and bundled math-library notices |
| OpenCV headless 4.11.0.86 | Apache-2.0 and exact wheel third-party notices |
| PyAV 14.2.0 / linked FFmpeg | PyAV license plus linked DLL build options, LGPL/GPL source and redistribution obligations; inspect exact wheel |
| tzdata 2026.6 | Python tzdata package notices and public-domain IANA timezone database provenance |
| ADB/platform-tools 37.0.1 (optional) | Exact archive notices and Android SDK download/redistribution terms; not bundled by default |
| scrcpy server 3.1 (optional) | Apache-2.0 and server dependencies/notices; digest pin does not replace license review |
| Tesseract (external/optional) | Exact executable and installed traineddata licenses; not bundled |
| PyInstaller 6.12.0 (build tool) | GPL bootloader exception and exact tool notices |
| Inno Setup 6 (optional build tool) | Selected compiler's current license and terms |

Original application vector icons use the project's design code; fonts are
system-selected. No signing key, account token or update credential belongs in
an artifact. Retain this review note with internal developer packages and replace
it with completed artifact-specific notices before public distribution.
