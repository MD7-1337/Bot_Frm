"""Real Qt controls with declared discovery fixtures; no Android hardware claim."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QListWidget, QWizard

from app.devices.adb import DeviceInfo
from app.devices.diagnostics import DiagnosticReport, DiagnosticStep
from app.ui.connection_wizard import ConnectionWizard
from app.ui.device_manager import DeviceManagerPanel


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    application = QApplication([])
    wizard = ConnectionWizard()
    wizard.show()
    application.processEvents()
    assert not wizard.discovery_page.isComplete() and not wizard.verify_page.isComplete()
    assert not wizard.home_button.isEnabled()
    QTest.mouseClick(wizard.prepared, Qt.MouseButton.LeftButton, pos=QPoint(8, wizard.prepared.height() // 2))
    QTest.mouseClick(wizard.button(QWizard.WizardButton.NextButton), Qt.MouseButton.LeftButton)
    assert wizard.currentId() == 1
    assert not wizard.button(QWizard.WizardButton.NextButton).isEnabled()

    simulated = "sim://" + "0" * 32
    wizard.update_state([DeviceInfo(simulated, "device")], simulated,
                        report_current=True, preview_ready=True)
    assert wizard.device_choice.count() == 1 and not wizard.discovery_page.isComplete()
    device = DeviceInfo("FIXTURE-SECRET", "unauthorized", "Fixture")
    wizard.update_state([device], device.serial)
    assert "unauthorized" in wizard.discovery_status.text()
    assert not wizard.discovery_page.isComplete()

    device = DeviceInfo(device.serial, "device", device.model)
    wizard.update_state([device], device.serial)
    assert wizard.discovery_page.isComplete() and not wizard.verify_page.isComplete()
    QTest.mouseClick(wizard.button(QWizard.WizardButton.NextButton), Qt.MouseButton.LeftButton)
    assert wizard.currentId() == 2
    requested = []
    wizard.diagnose_requested.connect(lambda: requested.append("diagnose"))
    QTest.mouseClick(wizard.diagnose_button, Qt.MouseButton.LeftButton)
    assert requested == ["diagnose"]

    report = DiagnosticReport(str(Path.home() / "fixture-adb"), serials=[device.serial])
    report.steps.append(DiagnosticStep("query", "Harmless query", "passed", f"{device.serial}: pairing code is 123456"))
    wizard.update_state([device], device.serial, report=report, report_current=True)
    assert not wizard.verify_page.isComplete()  # A list of serials is not query proof.
    report.verified_serial = device.serial
    wizard.update_state([device], device.serial, report=report, report_current=False, preview_ready=True)
    assert not wizard.verify_page.isComplete()
    wizard.update_state([device], device.serial, report=report, report_current=True)
    assert wizard.verify_page.isComplete() and not wizard.preview_page.isComplete()
    assert device.serial not in wizard.report_view.toPlainText() and "123456" not in wizard.report_view.toPlainText()
    QTest.mouseClick(wizard.button(QWizard.WizardButton.NextButton), Qt.MouseButton.LeftButton)
    assert wizard.currentId() == 3
    assert not wizard.button(QWizard.WizardButton.FinishButton).isEnabled()
    homes = []
    wizard.harmless_test_requested.connect(homes.append)
    wizard.update_state([device], device.serial, report=report, report_current=True, preview_ready=True)
    assert wizard.button(QWizard.WizardButton.FinishButton).isEnabled()
    QTest.mouseClick(wizard.home_button, Qt.MouseButton.LeftButton)
    assert homes == [device.serial]
    wizard.update_state([device], device.serial, report=report, report_current=False, preview_ready=True)
    assert not wizard.home_button.isEnabled() and not wizard.preview_page.isComplete()
    wizard.resize(700, 600)
    application.processEvents()
    assert wizard.width() <= 760 and wizard.home_button.visibleRegion().contains(wizard.home_button.rect().center())

    panel = DeviceManagerPanel(QListWidget(), QSettings(str(root / "wizard.ini"), QSettings.Format.IniFormat))
    panel.set_report(report)
    assert panel.redact_serials.isChecked()
    panel.show()
    panel.show_diagnostics()
    application.processEvents()
    target = root / "diagnostic.txt"
    original = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(target), "Text")
    try:
        QTest.mouseClick(panel.export_report_button, Qt.MouseButton.LeftButton)
    finally:
        QFileDialog.getSaveFileName = original
    text = target.read_text()
    assert device.serial not in text and "123456" not in text and str(Path.home()) not in text
    assert "[REDACTED]" in text and "[device-1]" in text
    wizard.close()
    panel.close()
    print(json.dumps({key: True for key in ("not_verified_without_phone", "simulation_excluded",
        "query_and_current_connection_required", "live_frame_required", "explicit_serial_home",
        "atomic_redacted_export", "compact_layout")}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
