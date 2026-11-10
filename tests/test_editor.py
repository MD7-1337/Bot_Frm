import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.editor.bridge import source_diagnostics


def test_valid_python_and_unicode():
    assert source_diagnostics('print("téléphone")\ntap(1, 2)\n') == []


def test_syntax_error_locations():
    diagnostics = source_diagnostics("x = 1\nif True print(x)\n")
    assert diagnostics[0]["line"] == 2
    assert diagnostics[0]["column"] > 0


def test_source_size_is_bounded():
    assert "limit" in source_diagnostics("x" * 1_000_001)[0]["message"]


def test_diagnostics_never_execute_python(tmp_path):
    sentinel = tmp_path / "must-not-exist"
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n"
    assert source_diagnostics(source) == []
    assert not sentinel.exists()


@pytest.mark.parametrize("url,blocked", [
    ("https://example.com/remote.js", True),
    ("http://127.0.0.1/private", True),
    ("file:///etc/passwd", True),
    ("qrc:///qtwebchannel/qwebchannel.js", False),
    ("qrc:///other-resource", True),
])
def test_editor_request_boundary(url, blocked):
    from PySide6.QtCore import QUrl
    from app.editor.widget import LocalRequests

    class Request:
        def requestUrl(self):
            return QUrl(url)

        def block(self, value):
            self.blocked = value

    request = Request()
    interceptor = LocalRequests()
    interceptor.interceptRequest(request)
    assert request.blocked is blocked


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Set STUDIO_GUI_TESTS=1 with desktop or documented headless Qt setup")
def test_real_monaco_webchannel_roundtrip():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tools/probe_editor.py")], cwd=root,
                            capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"roundtrip": true' in result.stdout
    assert '"syntax": true' in result.stdout


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Set STUDIO_GUI_TESTS=1 with desktop or documented headless Qt setup")
def test_integrated_workbench_starts_and_cleans_up(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path), STUDIO_CONFIG_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, "-m", "app.main", "--smoke"], cwd=root,
                            env=environment, capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"monaco_ready": true' in result.stdout
    assert '"dock_count": 3' in result.stdout
