"""The wizard's observation gates and export privacy, not phone acceptance."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.devices.diagnostics import DiagnosticReport, DiagnosticStep


@pytest.mark.parametrize("detail", ["pairing code: 123456", "pairing code 123456", "pairing code is 123456", "code=123456"])
def test_pairing_code_variations_are_never_exported(detail):
    report = DiagnosticReport("adb")
    report.steps.append(DiagnosticStep("query", "Query", "failed", detail))
    assert "123456" not in report.text(False)


@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("STUDIO_GUI_TESTS") != "1", reason="Real native connection-wizard controls")
def test_wizard_current_real_observations_and_redacted_export(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "tests/probe_connection_wizard.py"), str(tmp_path)],
                            cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("not_verified_without_phone", "simulation_excluded", "query_and_current_connection_required",
                  "live_frame_required", "explicit_serial_home", "atomic_redacted_export", "compact_layout"):
        assert f'"{check}": true' in result.stdout
