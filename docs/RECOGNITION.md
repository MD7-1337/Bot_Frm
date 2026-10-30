# Image, text and RGB recognition

**Visual Tools → Inspect text / color / pixels…** freezes the selected device/demo screenshot. Without a device it offers an explicitly chosen local raster screenshot. The inspector never sends input. Draw a rectangle, choose Image / Text / Color, configure settings, **Test recognition**, inspect real overlays/coordinates, then **Insert recognition Python** into Monaco. Hover or click a pixel to see original RGB/coordinates and insert `getPixel(x, y)`. Results describe the frozen source, not a future application state. Long result details remain available in the tooltip.

## Image matching

Existing RGB correlation, explicit scales, Region, target offsets, ambiguous-match errors and cross-scale overlap filtering are preserved. New `Pattern.preprocess("none" | "grayscale" | "threshold" | "edges")` applies the requested transformation to both search and template. Default `none` preserves prior behavior. Threshold uses Otsu; edges uses Canny (80/160). Per-image thresholds and edge boundary/hysteresis effects can lower scores even for a true crop. Preprocessing is an explicit experiment, not a promised accuracy improvement. Inspect results before lowering thresholds.

Coordinates remain in original screen pixels, independent of Qt scaling. Explicit scales resize templates (0.1–4, at most 16); there is no hidden rotation, perspective, DPI, lighting or animation normalization. After device rotation/resolution changes, capture fresh templates and coordinates. Constant or invalid templates fail explicitly; a real no-match is shown as zero results. Large searches run off the Qt thread; native OpenCV cancellation is checked around, not inside, a match operation.

## Optional local OCR

The implemented backend is **Tesseract 5-compatible TSV CLI** through stdin/stdout, with owned cancellable subprocesses, bounded timeouts and original-coordinate word boxes. It runs offline; nothing installs a system package or downloads a model at runtime. Configure an existing `tesseract` / `tesseract.exe` under **Settings → Recognition**, then **Check OCR engine / languages**. `STUDIO_TESSERACT` or PATH is also supported. The saved GUI path is passed explicitly to workers.

| Engine considered | Tradeoff and decision |
| --- | --- |
| Tesseract | Offline CPU CLI, Windows/Linux executables, Apache-2.0 engine, local traineddata; no Python ML runtime. Selected optional adapter. Typical fast language data is a few MB, with actual size depending on the chosen file/build. |
| EasyOCR / PaddleOCR | Multilingual detectors and richer scene-text capabilities, but larger native/ML dependencies and model acquisition complexity. Deferred on this disk-limited target. |
| OS/cloud OCR | Platform/service coupling and possible networking/credentials. Not required for core offline use. |

On an Ubuntu machine where you are permitted to install optional system dependencies: `sudo apt-get install tesseract-ocr tesseract-ocr-eng`. This is **optional**; on a school computer use an IT-provided executable and language data instead. On Windows point Settings at an existing trusted compatible distribution; configure `TESSDATA_PREFIX` for its local traineddata if needed. No Windows Tesseract distribution is bundled/tested. Check third-party build/model licensing before redistribution. Missing engine/data raises `OCRUnavailable` with configuration guidance, not a false no-text result.

Implemented short and `device` APIs:

- `recognizeText(*, region=None, language="eng", confidence=0, timeout=10, psm=6, preprocess="grayscale") -> OCRResult`: full text plus immutable device-bound word `TextMatch` boxes. Confidence is 0–100, not certainty.
- `readText(...) -> str`: same options, empty string only for an actual text-free result.
- `findText(text, *, region=None, exact=True, case_sensitive=False, confidence=50, language="eng", timeout=10) -> list[TextMatch]`: same-line word/phrase search. Exact means normalized whitespace plus whole words; tolerant mode uses substring matching, not fuzzy edit distance. Casefolding is default.
- `textExists(...) -> bool`: same search options, errors propagate.
- `waitText(text, timeout=10, *, region=None, exact=True, case_sensitive=False, confidence=50, language="eng", poll_interval=.2) -> TextMatch`: unique match or `AmbiguousMatch`; bounded wall-clock timeout includes capture/OCR/pause. Zero requests one OCR attempt bounded to 10 seconds. No auto-reconnection/replay.

`click(text_match)` checks assigned device and source dimensions before tapping its center. `OCRUnavailable`, `OCRFailed` and `RecognitionTimeout` distinguish missing dependencies, native/output failures and deadlines. Native OCR timeout must be >0 and ≤60 seconds, search area ≤4 MP, supported PSM 3/6/7/11/12/13. Small inputs are scaled 2× for OCR and boxes are mapped back. A subprocess checks cancellation/pause approximately every 100 ms and is killed/reaped when interrupted. Model/CLI startup costs apply to each fresh OCR capture. Punctuation, small/animated/stylized text and uninstalled languages remain limitations.

## RGB

`getPixel` captures fresh RGB. `findColor((r,g,b), tolerance=0, region=..., limit=100)` uses inclusive per-channel differences and returns row-major pixel locations. The inspector samples actual source pixels, bounds displayed results to 100 and draws 1-pixel overlays. Colors identify pixels, not object clusters. It uses the existing runtime APIs, not a separate simulated matcher.

Use Regions to reduce image/color/OCR cost. Reproduce this increment's fixture measurements with `.venv/bin/python tools/benchmark_recognition.py`; results and limitations are in [validation](PHASE6_VALIDATION.md).
