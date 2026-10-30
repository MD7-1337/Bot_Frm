"""Shared Qt design tokens and vector icons; no additional UI runtime."""
from __future__ import annotations

from dataclasses import dataclass
import sys

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer


@dataclass(frozen=True)
class Theme:
    background: str
    surface: str
    raised: str
    border: str
    text: str
    muted: str
    accent: str
    selection: str
    danger: str


THEMES = {
    "dark": Theme("#11151e", "#191f2c", "#222b3b", "#303b50", "#e7edf8", "#a9b6cc", "#75a7ff", "#283f67", "#ff8e9a"),
    "light": Theme("#eef2f8", "#ffffff", "#f3f6fb", "#ced7e5", "#1b2941", "#50617b", "#235fc5", "#dce9ff", "#b82743"),
}
# Original, small line icons. Labels/accessibility names remain available.
PATHS = {
    "studio": '<path d="m8 6-5 6 5 6m8-12 5 6-5 6m-3-15-2 18"/>',
    "devices": '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 18h4"/>',
    "visual": '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m3 17 6-6 4 4 3-3 6 6"/><circle cx="16" cy="8" r="1"/>',
    "recorder": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    "monitor": '<path d="M2 12h4l3-8 6 16 3-8h4"/>',
    "settings": '<circle cx="12" cy="12" r="4"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2"/>',
    "tasks": '<rect x="4" y="3" width="16" height="19" rx="2"/><path d="m7 9 2 2 3-4m1 9h4m-10 0h2"/>',
    "run": '<path d="m7 3 14 9-14 9z"/>',
    "pause": '<path d="M8 4v16M16 4v16"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "add": '<path d="M12 4v16M4 12h16"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 14-2l1 2M4 16l1 2a8 8 0 0 0 14-2"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    "folder": '<path d="M2 6h8l2 3h10v12H2zM2 6V3h7l3 3"/>',
}


def icon(name, color="#a9b6cc"):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{PATHS.get(name, PATHS["studio"])}</g></svg>'
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    result = QIcon(pixmap)
    return result


def apply_theme(application, name="dark"):
    theme = THEMES.get(name, THEMES["dark"])
    application.setStyle("Fusion")
    font = QFont("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 10)
    application.setFont(font)
    palette = QPalette()
    for role, value in ((QPalette.ColorRole.Window, theme.background), (QPalette.ColorRole.Base, theme.surface),
                        (QPalette.ColorRole.AlternateBase, theme.raised), (QPalette.ColorRole.WindowText, theme.text),
                        (QPalette.ColorRole.Text, theme.text), (QPalette.ColorRole.Button, theme.raised),
                        (QPalette.ColorRole.ButtonText, theme.text), (QPalette.ColorRole.Highlight, theme.selection),
                        (QPalette.ColorRole.HighlightedText, theme.text), (QPalette.ColorRole.ToolTipBase, theme.raised),
                        (QPalette.ColorRole.ToolTipText, theme.text)):
        palette.setColor(role, QColor(value))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.muted))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.muted))
    application.setPalette(palette)
    application.setStyleSheet(f'''
        QWidget {{ color: {theme.text}; }}
        QMainWindow, QWidget#workspaceShell {{ background: {theme.background}; }}
        QMenuBar, QMenu, QToolBar {{ background: {theme.surface}; spacing: 6px; border: none; }}
        QToolBar {{ padding: 6px; border-bottom: 1px solid {theme.border}; }}
        QMenu::item {{ padding: 8px 22px; }}
        QMenu::item:selected {{ background: {theme.selection}; }}
        QWidget#sidebar, QFrame#surface {{ background: {theme.surface}; border: 1px solid {theme.border}; border-radius: 10px; }}
        QLabel#brand {{ font-size: 18px; font-weight: 700; color: {theme.accent}; }}
        QLabel#eyebrow {{ color: {theme.accent}; font-size: 10px; font-weight: 700; }}
        QLabel#workspaceTitle {{ font-size: 24px; font-weight: 700; }}
        QLabel#sectionTitle {{ font-size: 14px; font-weight: 600; }}
        QLabel#muted {{ color: {theme.muted}; }}
        QLabel#notice {{ background: {theme.raised}; padding: 12px; border-radius: 8px; color: {theme.muted}; }}
        QLabel[severity="error"] {{ color: {theme.danger}; }}
        QToolButton#navButton {{ text-align: left; border: none; border-radius: 8px; padding: 10px 12px; min-height: 24px; }}
        QToolButton#navButton:hover, QToolButton#navButton:checked {{ background: {theme.selection}; color: {theme.accent}; }}
        QPushButton, QToolButton {{ background: {theme.raised}; border: 1px solid {theme.border}; border-radius: 6px; padding: 7px 12px; min-height: 18px; }}
        QPushButton:hover, QToolButton:hover {{ border-color: {theme.accent}; }}
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {theme.accent}; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {theme.muted}; background: {theme.surface}; }}
        QPushButton#primary {{ background: {theme.accent}; color: {theme.background}; font-weight: 600; border: none; }}
        QPushButton#primary:disabled {{ background: {theme.raised}; color: {theme.muted}; border: 1px solid {theme.border}; }}
        QPushButton#emergency {{ color: {theme.danger}; border-color: {theme.danger}; font-weight: 600; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {theme.surface}; border: 1px solid {theme.border}; border-radius: 5px; padding: 6px 8px; min-height: 18px; selection-background-color: {theme.selection}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QListWidget, QTreeWidget, QTreeView, QTableWidget, QPlainTextEdit {{ background: {theme.surface}; border: 1px solid {theme.border}; border-radius: 7px; selection-background-color: {theme.selection}; outline: none; }}
        QListWidget::item {{ padding: 10px; border-bottom: 1px solid {theme.border}; }}
        QListWidget::item:selected {{ background: {theme.selection}; border-left: 3px solid {theme.accent}; }}
        QHeaderView::section {{ background: {theme.raised}; border: none; padding: 8px; color: {theme.muted}; }}
        QGroupBox {{ border: 1px solid {theme.border}; border-radius: 8px; margin-top: 16px; padding: 16px 10px 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {theme.muted}; }}
        QTabWidget::pane {{ border: none; }}
        QTabBar::tab {{ background: {theme.surface}; color: {theme.muted}; padding: 10px 14px; border-bottom: 2px solid transparent; }}
        QTabBar::tab:selected {{ color: {theme.accent}; border-bottom: 2px solid {theme.accent}; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: {theme.surface}; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {theme.border}; border-radius: 5px; min-height: 32px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QSplitter::handle {{ background: {theme.background}; }}
        QProgressBar {{ border: none; border-radius: 3px; background: {theme.raised}; max-height: 6px; }}
        QProgressBar::chunk {{ background: {theme.accent}; border-radius: 3px; }}
        QStatusBar {{ background: {theme.surface}; color: {theme.muted}; }}
        QToolTip {{ padding: 8px; border: 1px solid {theme.border}; }}
    ''')
    return theme
