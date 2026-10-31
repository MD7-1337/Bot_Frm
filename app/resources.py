"""Read-only resources in a source checkout or a PyInstaller application."""
from pathlib import Path
import sys


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
