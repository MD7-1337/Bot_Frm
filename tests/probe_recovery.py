"""Real Qt Widgets persistence view and recorder metadata journey."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.automation.recording import ActionRecorder, ScreenshotEvidence
from app.automation.recovery_journal import RecoveryJournal
from app.ui.recorder_panel import RecorderPanel
from app.ui.recovery_panel import RecoveryPanel


def main():
    root = Path(sys.argv[1])
    app = QApplication([])
    journal = RecoveryJournal(root / "failures.sqlite3")
    panel = RecoveryPanel(journal)
    panel.resize(1000, 700)
    panel.show()
    app.processEvents()
    assert not panel.capture_failures.isChecked()
    QTest.mouseClick(panel.capture_failures, Qt.MouseButton.LeftButton,
                     pos=QPoint(8, panel.capture_failures.height() // 2))
    assert panel.capture_failures.isChecked()
    image = np.random.default_rng(2).integers(0, 255, (30, 40, 3), dtype=np.uint8)
    screen = ScreenshotEvidence("phone-one", cv2.imencode(".png", image)[1].tobytes(), (40, 30))
    record_id = panel.record_event({"event": "error", "run_id": "run-one", "serial": "phone-one",
                                   "error_type": "RecognitionTimeout", "message": "target absent",
                                   "source_path": "main.py", "source_line": 2,
                                   "traceback": "TRACEBACK EVIDENCE", "failure": {"category": "recognition", "advice": "Inspect current screen"}}, screen)
    app.processEvents()
    assert panel.table.rowCount() == 1
    assert "TRACEBACK EVIDENCE" in panel.details.toPlainText()
    assert panel.screenshot.pixmap() is not None and not panel.screenshot.pixmap().isNull()
    assert journal.detail(record_id)["has_screenshot"]
    panel.close()
    reopened = RecoveryPanel(RecoveryJournal(root / "failures.sqlite3"))
    reopened.show()
    app.processEvents()
    assert reopened.table.rowCount() == 1
    assert "target absent" in reopened.details.toPlainText()
    reopened.close()

    recorder = ActionRecorder()
    recorder.start("phone-one", 1)
    recorder.complete(recorder.ticket("phone-one", 1, "tap(10,20)", .05), 100, evidence=screen)
    recorder.complete(recorder.ticket("phone-one", 1, "back()", .1), 100.4)
    recorder.stop()
    timeline = RecorderPanel(recorder)
    timeline.resize(1000, 700)
    timeline.show()
    app.processEvents()
    assert timeline.table.rowCount() == 3
    timeline.table.selectRow(2)
    assert "recorded at +0.400s" in timeline.step_info.text()
    QTest.mouseClick(timeline.buttons["Move up"], Qt.MouseButton.LeftButton)
    app.processEvents()
    timeline.source()
    assert recorder.actions == ["tap(10,20)", "back()", "sleep(0.350)"]
    assert recorder.timestamps == {0: 0., 1: 100.4-100}
    assert recorder.evidence == {0: screen}
    timeline.table.selectRow(0)
    QTest.mouseClick(timeline.buttons["Delete step"], Qt.MouseButton.LeftButton)
    app.processEvents()
    timeline.source()
    assert recorder.actions == ["back()", "sleep(0.350)"]
    assert recorder.timestamps == {0: 100.4-100}
    assert recorder.evidence == {}
    timeline.table.item(0, 0).setText("sleep(1e999)")
    timeline.source()
    assert recorder.durations[0] == 0.
    restored = ActionRecorder()
    restored.load_session(recorder.session_json())
    assert restored.actions[0] == "sleep(1e999)"
    timeline.close()
    print(json.dumps({"failure_history": True, "private_evidence": True, "recorder_metadata": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
