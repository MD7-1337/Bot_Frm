# Built only on Windows x64, using tools/build_windows.py.
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
# This application uses Qt Widgets and QtWebEngineWidgets, not Python QML/Quick
# APIs. Their hooks collect every installed QML plugin, including unused GPL-only
# Charts/Graphs/DataVisualization modules. Exclude only unused Python bindings;
# PyInstaller still resolves required native QtQuick/Qml library dependencies.
unused_qml_bindings = ["PySide6." + name for name in (
    "QtQml", "QtQuick", "QtQuickWidgets", "QtWebEngineQuick",
    "QtQuick3D", "QtCharts", "QtDataVisualization", "QtGraphs", "QtGraphsWidgets")]
datas = [(str(root / "editor_web"), "editor_web"),
         (str(root / "build" / "release-notices"), "THIRD_PARTY_NOTICES")]
datas += collect_data_files("app")
datas += collect_data_files("tzdata")
for dependency in ("android-automation-studio", "PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6", "numpy", "opencv-python-headless", "av", "tzdata"):
    datas += copy_metadata(dependency)
# Android SDK downloads are optional external tools by default. A deliberate
# local developer build can include the reviewed artifacts and their notices.
if os.environ.get("STUDIO_BUNDLE_ANDROID_TOOLS") == "1":
    datas.append((str(root / ".tools"), ".tools"))

a = Analysis([str(root / "packaging" / "windows_entry.py")],
             pathex=[str(root)], datas=datas,
             hiddenimports=collect_submodules("app") + collect_submodules("tzdata"),
             excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", *unused_qml_bindings],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="AndroidAutomationStudio", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False,
          version=str(root / "build/windows-version-info.txt"),
          console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name="AndroidAutomationStudio")
