"""Collect standard QtGui dependencies without the unused virtual keyboard.

The desktop application uses host keyboard/IME input. Qt's separately licensed
Virtual Keyboard input-context plugin is optional and otherwise pulls its GPL
module into the package during native dependency scanning. Filter that plugin
before scanning; retain all standard platform and host IME plugins.
"""
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [entry for entry in binaries
            if not entry[0].replace("\\", "/").rsplit("/", 1)[-1].lower().startswith(
                ("libqtvirtualkeyboardplugin.", "qtvirtualkeyboardplugin."))]
