"""Linux one-folder build; run on the oldest supported glibc baseline."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
# Do not collect the unused Python QML/Quick APIs: their hooks otherwise gather
# every installed QML plugin, including GPL-only Charts/Graphs/DataVisualization.
# Required native QtQuick/Qml dependencies remain subject to normal DLL scanning.
unused_qml_bindings = ["PySide6." + name for name in (
    "QtQml", "QtQuick", "QtQuickWidgets", "QtWebEngineQuick",
    "QtQuick3D", "QtCharts", "QtDataVisualization", "QtGraphs", "QtGraphsWidgets")]
datas = [(str(root / "editor_web"), "editor_web"),
         (str(root / "build/release-notices"), "THIRD_PARTY_NOTICES")]
datas += collect_data_files("app") + collect_data_files("tzdata")
for dependency in ("android-automation-studio", "PySide6", "PySide6-Essentials", "PySide6-Addons",
                   "shiboken6", "numpy", "opencv-python-headless", "av", "tzdata"):
    datas += copy_metadata(dependency)

a = Analysis([str(root / "packaging/windows_entry.py")], pathex=[str(root)], datas=datas,
             hiddenimports=collect_submodules("app") + collect_submodules("tzdata"),
             excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", *unused_qml_bindings], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AndroidAutomationStudio",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AndroidAutomationStudio")
