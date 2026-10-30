"""Real image/OCR/color tests on one frozen source; no device input is dispatched."""
from __future__ import annotations

import json
from pathlib import Path
import time
import threading

from PySide6.QtCore import QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                              QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QSpinBox,
                              QSplitter, QTabWidget, QVBoxLayout, QWidget)

from app.ui.capture_dialog import SelectionCanvas, _MatchJob, image_rgb
from app.ui.components import button, label, scroll
from app.ui.visual_tools import load_asset
from app.vision.matching import Match, Region, find_scaled, validate_scales
from app.vision.color import find_color
from app.vision.ocr import TesseractOCR, search_text


class RecognitionInspector(QDialog):
    code_ready = Signal(str)
    tested = Signal(object)

    def __init__(self, frame, source, project_root, *, ocr_executable=None, reference="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recognition Inspector")
        self.resize(1120,800)
        self.frame=frame.copy()
        self.project_root=Path(project_root)
        self.ocr_executable=ocr_executable
        self._busy=False
        self._closing=False
        self._job=None
        self._pixel=None
        self._cancel=threading.Event()
        self.pool=QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        layout=QVBoxLayout(self)
        layout.addWidget(label("Frozen source: "+source,"notice"))
        split=QSplitter()
        self.canvas=SelectionCanvas(self.frame)
        self.canvas.pixel_hovered.connect(self._pixel_changed)
        split.addWidget(self.canvas)
        properties=QWidget()
        forms=QVBoxLayout(properties)
        forms.addWidget(label("RECOGNITION INSPECTOR","eyebrow"))
        self.pixel_label=label("Hover or select a pixel for original coordinates and RGB.","notice")
        forms.addWidget(self.pixel_label)
        forms.addWidget(button("Insert selected pixel code",self.insert_pixel))
        self.use_region=QCheckBox("Search only the selected rectangle")
        forms.addWidget(self.use_region)
        self.tabs=QTabWidget()
        self.tabs.setDocumentMode(True)
        image=QWidget(); image_form=QFormLayout(image)
        self.image_path=QLineEdit(reference)
        image_form.addRow("Project image",self.image_path)
        image_form.addRow(button("Choose target…",self.choose_target))
        self.similarity=QDoubleSpinBox(); self.similarity.setRange(0,1); self.similarity.setValue(.9); self.similarity.setSingleStep(.01)
        image_form.addRow("Minimum score",self.similarity)
        self.scales=QLineEdit("1")
        image_form.addRow("Explicit scales",self.scales)
        self.preprocessing=QComboBox(); self.preprocessing.addItems(["none","grayscale","threshold","edges"])
        image_form.addRow("Preprocessing",self.preprocessing)
        self.tabs.addTab(image,"Image")
        text=QWidget(); text_form=QFormLayout(text)
        self.query=QLineEdit("START")
        self.language=QLineEdit("eng"); self.language.setMaxLength(100)
        self.confidence=QDoubleSpinBox(); self.confidence.setRange(0,100); self.confidence.setValue(50)
        self.exact=QCheckBox("Exact words / phrase"); self.exact.setChecked(True)
        text_form.addRow("Query (blank = all)",self.query)
        text_form.addRow("Language",self.language)
        text_form.addRow("Minimum confidence",self.confidence)
        text_form.addRow(self.exact)
        text_form.addRow(label("Local Tesseract and language data are optional. Confidence is an engine estimate, not certainty; missing dependencies are reported explicitly."))
        self.tabs.addTab(text,"Text / OCR")
        color=QWidget(); color_form=QFormLayout(color)
        self.rgb=QLineEdit("105, 165, 255")
        self.tolerance=QSpinBox(); self.tolerance.setRange(0,255)
        color_form.addRow("RGB",self.rgb); color_form.addRow("Per-channel tolerance",self.tolerance)
        color_form.addRow(label("Hover a pixel to sample it. Color results are individual pixels, not detected objects; overlays show at most 100."))
        self.tabs.addTab(color,"Color")
        forms.addWidget(self.tabs)
        self.test_button=button("Test recognition",self.start_test,primary=True)
        forms.addWidget(self.test_button)
        forms.addWidget(button("Insert recognition Python",self.insert_code))
        self.result=label("Choose a method and run a real recognition test.","notice")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        forms.addWidget(self.result)
        forms.addStretch()
        split.addWidget(scroll(properties)); split.setSizes([660,420])
        layout.addWidget(split,stretch=1)
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(self.reject); layout.addWidget(controls)

    def _pixel_changed(self,x,y,color):
        self._pixel=(x,y,color)
        self.pixel_label.setText(f"Original pixels: ({x}, {y}) · RGB {color}")
        self.rgb.setText(", ".join(map(str,color)))

    def _region(self):
        if self.use_region.isChecked():
            if self.canvas.selection is None:
                raise ValueError("Draw a search rectangle first")
            return self.canvas.selection
        return None

    def choose_target(self):
        path,_=QFileDialog.getOpenFileName(self,"Choose project image target",str(self.project_root / "images"),"Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            try:
                relative=Path(path).resolve().relative_to(self.project_root)
                self.image_path.setText(relative.as_posix())
            except ValueError:
                self.result.setText("Choose an image inside this project; import/copy other targets explicitly first.")

    def start_test(self):
        if self._busy or self._closing:
            return
        try:
            region=self._region()
            mode=self.tabs.currentIndex()
            frame=image_rgb(self.frame)
            threshold=self.similarity.value()
            scales=validate_scales(tuple(float(x.strip()) for x in self.scales.text().split(','))) if mode==0 else (1,)
            reference=self.image_path.text(); preprocessing=self.preprocessing.currentText()
            query=self.query.text(); language=self.language.text(); confidence=self.confidence.value(); exact=self.exact.isChecked()
            color=tuple(int(x.strip()) for x in self.rgb.text().split(',')) if mode==2 else None
            tolerance=self.tolerance.value()
        except (ValueError,TypeError) as error:
            self.result.setText(str(error)); return
        def operation():
            def check():
                if self._cancel.is_set():
                    raise RuntimeError("Recognition cancelled")
            check()
            started=time.perf_counter()
            if mode==0:
                template=image_rgb(load_asset(self.project_root,reference))
                matches=find_scaled(frame,template,threshold,region,scales=scales,preprocess=preprocessing)
                detail=f"{len(matches)} image match(es); scores are normalized correlation, not probability."
            elif mode==1:
                ocr=TesseractOCR(self.ocr_executable).recognize(frame,region=region,language=language,confidence=confidence,checkpoint=check)
                words=search_text(ocr,query,exact=exact) if query.strip() else list(ocr.words)
                matches=[Match(word.region,word.confidence/100) for word in words]
                detail=f"{len(words)} OCR match(es). Text: {ocr.text[:600]}\n" + " | ".join(f"{w.text!r}: {w.confidence:.1f}/100 at {w.region}" for w in words[:8])
            else:
                points=find_color(frame,color,tolerance,region,limit=100)
                matches=[Match(Region(p.x,p.y,1,1),1.) for p in points]
                detail=f"{len(points)} matching pixels (limit 100), per-channel tolerance {tolerance}. " + str(points[:8])
            detail+=f"\nRecognition: {(time.perf_counter()-started)*1000:.1f} ms; no tap was sent."
            check()
            if mode==0:
                detail+="\n" + " | ".join(f"{m.score:.3f}: {m.region}" for m in matches[:8])
            return matches,detail
        self._cancel.clear()
        self._busy=True; self.test_button.setEnabled(False); self.result.setText("Recognizing off the GUI thread…")
        self._job=_MatchJob(operation)
        self._job.signals.done.connect(self._done,Qt.ConnectionType.QueuedConnection)
        self.pool.start(self._job)

    @Slot(object,object)
    def _done(self,result,error):
        self._busy=False; self._job=None
        if self._closing:
            super().reject(); return
        self.test_button.setEnabled(True)
        self.canvas.matches=[] if error else result[0][:100]
        self.canvas.update()
        self.result.setText("Recognition failed: "+error if error else result[1])
        self.tested.emit({"error":error,"matches":[] if error else result[0]})

    def insert_pixel(self):
        if self._pixel is None:
            self.result.setText("Hover or click a screenshot pixel first."); return
        x,y,color=self._pixel
        self.code_ready.emit(f"pixel = getPixel({x}, {y})  # sampled RGB {color}\n")

    def insert_code(self):
        try:
            region=self._region()
            bounds=f", region=Region({region.x}, {region.y}, {region.width}, {region.height})" if region else ""
            mode=self.tabs.currentIndex()
            if mode==0:
                scales=validate_scales(tuple(float(x.strip()) for x in self.scales.text().split(',')))
                pattern=f"Pattern({json.dumps(self.image_path.text())}).similar({self.similarity.value()}).atScales({', '.join(map(str,scales))}).preprocess({self.preprocessing.currentText()!r})"
                if region:
                    pattern+=f".inRegion(Region({region.x}, {region.y}, {region.width}, {region.height}))"
                code=f"matches = findAll({pattern})\n"
            elif mode==1:
                code=(f"matches = findText({json.dumps(self.query.text())}, exact={self.exact.isChecked()}, confidence={self.confidence.value()}, language={json.dumps(self.language.text())}{bounds})\n" if self.query.text().strip()
                      else f"text = readText(language={json.dumps(self.language.text())}{bounds})\n")
            else:
                color=tuple(int(x.strip()) for x in self.rgb.text().split(','))
                if len(color)!=3 or any(not 0<=x<=255 for x in color):
                    raise ValueError("RGB requires three channels in [0,255]")
                code=f"pixels = findColor({color}, tolerance={self.tolerance.value()}{bounds})\n"
            compile(code,"<recognition insertion>","exec")
            self.code_ready.emit(code)
        except (ValueError,TypeError,SyntaxError) as error:
            self.result.setText(str(error))

    def reject(self):
        if self._busy:
            self._closing=True
            self._cancel.set()
            self.result.setText("Waiting for the bounded recognition operation to finish…")
            return
        super().reject()

    def closeEvent(self,event):
        if self._busy:
            self._closing=True; self._cancel.set(); event.ignore()
        else:
            super().closeEvent(event)
