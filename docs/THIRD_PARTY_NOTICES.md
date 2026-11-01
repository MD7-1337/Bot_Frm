# Release notice and license review

This repository does not currently supply an application LICENSE file. Establish
the project's distribution license before making a public binary release. Build
outputs are developer review artifacts, not a claim of distribution clearance.

## Recovery review — 2026-11-01

Public binary redistribution remains **BLOCKED**. The owner must choose the
application's distribution license; this review does not choose one. In addition,
the exact deployed Qt/Chromium notices, source correspondence and replacement
procedure have not yet been verified. A successful build or metadata inventory
does not clear these requirements.

The builders now generate `windows-payload-inventory.json` or
`linux-payload-inventory.json` from the actual frozen payload before archiving.
The package includes the same report as `PAYLOAD_INVENTORY.json`. Every ordinary
payload file has a SHA-256 and size; contained Linux library aliases record their
link target. The inventory excludes itself and describes the payload, not the
outer ZIP/installer. Archive checksums remain separate. This evidence permits
native-library reconciliation; it is deliberately not a completed license map.

When `STUDIO_LGPL_RUNTIME_DIR` is configured, notice collection now rejects an
external or incomplete FFmpeg prefix, verifies the repaired wheel hash, compares
every installed PyAV/FFmpeg native file with that wheel, verifies the included
FFmpeg/PyAV source archives and build script, and copies their notices and source
into the frozen package. Previously this copy was documented but not implemented.
Ordinary developer builds without that environment setting remain possible and
remain blocked from redistribution. PyInstaller distribution notices and available
CPython installation license text are also retained. Missing or incomplete
CPython notices still require resolution for the selected native Python build.

Qt's LGPL route requires more than dynamic DLLs: document the chosen license for
each deployed module, corresponding source and modifications, replacement or
relinking instructions, applicable installation information, and recipient rights.
The one-folder layout leaves native libraries outside the executable, but actual
replacement with a compatible rebuilt Qt/PySide library has not been tested.
QtWebEngine also embeds Chromium components with separate licenses. Obtain the
notices and corresponding sources matching the actual 6.8.3 wheel binaries;
the rolling online documentation is a reference, not artifact evidence.

Primary review references: [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations),
[Qt 6.8 WebEngine licensing](https://doc.qt.io/qt-6.8/qtwebengine-licensing.html),
and [Qt for Python 6.8 deployment](https://doc.qt.io/qtforpython-6.8/deployment/index.html).
The first-party guidance confirms separate third-party obligations; it does not
certify this application's artifacts.

### Exact installed Qt wheel inspection

The recovery environment's installed Linux wheels are PySide6,
PySide6-Essentials, PySide6-Addons and shiboken6 **6.8.3**. Searching each installed
distribution's RECORD for license, licence, notice, copying and copyright file
names found **no supplied license/notice text files**. Their METADATA declares
`LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; that declaration cannot substitute
for required license text or Chromium third-party notices. Windows wheels must
be inspected independently. The collector records an explicit missing-notice
status and retains each distribution's METADATA, WHEEL and RECORD with hashes.

Direct installed-library queries report Qt **6.8.3**, QtWebEngine **6.8.3** and
Chromium **122.0.6261.171** on this Linux environment. Builds now save the same
queries to `THIRD_PARTY_NOTICES/Qt-build-information.json`; no GUI or network is
started by these queries. Native Windows results must come from its own build.

The official [PySide6 6.8.3 source directory](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/)
offers `pyside-setup-everywhere-src-6.8.3.tar.xz`.
The official [Qt 6.8.3 submodule source directory](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/)
offers `qtwebengine-everywhere-src-6.8.3.tar.xz` (approximately 540 MB), plus
QtBase, QtDeclarative and other module sources. These are actionable source
candidates; their existence alone does not prove matching wheel configuration,
patches or complete corresponding source. Retrieve verified upstream checksums,
retain the exact source and build information for every deployed module, extract
and reconcile the third-party notices, then validate replacement. No archive
download, source correspondence or redistribution clearance is claimed here.

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
