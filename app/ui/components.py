"""Small reusable surfaces, headings and actions."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout


class Notice(QLabel):
    """Keep long backend errors from displacing the workspace; retain full tooltip."""
    def setText(self, text):
        text = str(text)
        self.setToolTip(text)
        super().setText(text if len(text) <= 320 else text[:317] + "…")


def label(text, role="muted", *, wrap=True):
    widget = Notice(text) if role == "notice" else QLabel(text)
    widget.setObjectName(role)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def button(text, callback, *, primary=False, tooltip=None):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(lambda checked=False: callback())
    widget.setToolTip(tooltip or text)
    return widget


def surface():
    widget = QFrame()
    widget.setObjectName("surface")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    return widget, layout


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area
