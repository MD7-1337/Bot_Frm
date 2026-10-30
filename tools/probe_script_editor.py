"""Real Monaco provider/bridge exercise, using explicit local image fixtures."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import time

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.editor.widget import EditorWidget


def spin(app, condition, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError("Editor provider/bridge probe timed out")


def main(directory: Path):
    (directory / "images").mkdir(parents=True, exist_ok=True)
    image = QImage(40, 30, QImage.Format.Format_RGB32)
    image.fill(QColor("#7c40bc"))
    assert image.save(str(directory / "images/téléphone.png"), "PNG")
    app = QApplication([])
    widget = EditorWidget()
    widget.set_project_root(directory)
    widget.resize(1000, 700)
    widget.show()
    spin(app, lambda: widget.is_ready)

    def js(expression):
        results = []
        widget.page.runJavaScript(expression, results.append)
        spin(app, lambda: bool(results))
        return results[0]

    checks = {}
    catalog = json.loads(js("JSON.stringify(window.studio.apiCatalog)"))
    checks["catalog"] = {item["name"] for item in catalog} >= {"click", "waitImage", "doubleClick", "Pattern", "Region"}
    widget.set_text("device.")
    spin(app, lambda: widget.source == "device.")
    completion = json.loads(js("JSON.stringify(window.studio.completionItems(window.studio.editor.getModel(),{lineNumber:1,column:8}))"))
    checks["completion"] = {item["label"] for item in completion["suggestions"]} >= {"click", "capture", "waitVanish", "launchApp"}
    assert not any(item["label"] == "Pattern" for item in completion["suggestions"])
    widget.set_text('device.waitImage("téléphone.png", ')
    signature = json.loads(js("JSON.stringify(window.studio.signatureAt(window.studio.editor.getModel(),{lineNumber:1,column:window.studio.editor.getModel().getLineMaxColumn(1)}))"))
    checks["signature"] = signature["activeParameter"] == 1 and "timeout" in signature["signatures"][0]["label"]
    source = 'click("téléphone.png")\nwaitImage("missing.png", timeout=1)\n'
    widget.set_text(source)
    spin(app, lambda: widget.source == source)
    spin(app, lambda: len(json.loads(js("JSON.stringify(window.studio.imageReferences)"))) == 2)
    references = json.loads(js("JSON.stringify(window.studio.imageReferences)"))
    reference = next(item for item in references if item["reference"] == "téléphone.png")
    position = json.dumps({"lineNumber": reference["start_line"], "column": reference["start_column"] + 1})
    js("window.__imageHover = null; window.studio.hoverAt(window.studio.editor.getModel()," + position + ").then(value => {window.__imageHover=value;}); true")
    spin(app, lambda: bool(js("window.__imageHover !== null")))
    hover = json.loads(js("JSON.stringify(window.__imageHover)"))
    checks["image_hover"] = any("data:image/png;base64," in item["value"] for item in hover["contents"])
    js("window.studio.editor.focus(); window.studio.editor.setPosition(" + position + "); window.studio.editor.getAction('editor.action.showHover').run(); true")
    spin(app, lambda: js("Array.from(document.querySelectorAll('.monaco-hover img')).some(image => image.complete && image.naturalWidth === 40 && image.naturalHeight === 30)"))
    checks["image_hover"] = checks["image_hover"] and bool(js("document.querySelector('.monaco-hover img').src.startsWith('data:image/png;base64,')"))
    markers = json.loads(js("JSON.stringify(monaco.editor.getModelMarkers({owner:'image-assets'}))"))
    checks["missing_warning"] = len(markers) == 1 and markers[0]["startLineNumber"] == 2
    widget.set_execution_line(2)
    widget.set_run_status("fixture-phone · paused")
    checks["execution_line"] = js("window.studio.executionLine") == 2 and js("window.studio.runStatus") == "fixture-phone · paused"
    checks["plain_python"] = js("window.studio.getText()") == source
    ast.parse(widget.source)
    widget.set_execution_line(None)
    assert js("window.studio.executionLine === null") is True
    print(json.dumps(checks), flush=True)
    widget.shutdown()
    widget.close()
    app.processEvents()
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
