"""Optional offline Tesseract TSV adapter. No downloads, shell or Qt dependency."""
from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import cv2
import numpy as np

from app.vision.matching import Region, _image


class OcrUnavailable(RuntimeError):
    """Executable or language data unavailable; configure locally, never auto-download."""


class OcrFailure(RuntimeError):
    """The OCR process/output failed; this is not a legitimate no-text result."""


@dataclass(frozen=True)
class TextBox:
    text: str
    confidence: float
    region: Region
    line: tuple[int, int, int, int]


@dataclass(frozen=True)
class TextResult:
    text: str
    words: tuple[TextBox, ...]


def parse_tsv(payload: str, *, scale=1, origin=(0,0), size=None, confidence=0):
    if not isinstance(payload, str) or len(payload.encode("utf-8")) > 4_000_000:
        raise OcrFailure("OCR output exceeds its supported limit")
    if not payload.startswith("level\t"):
        raise OcrFailure("Tesseract returned no supported TSV header")
    words = []
    lines = {}
    try:
        rows = csv.DictReader(io.StringIO(payload), delimiter="\t", quoting=csv.QUOTE_NONE)
        required = {"level", "page_num", "block_num", "par_num", "line_num", "left", "top", "width", "height", "conf", "text"}
        if not required <= set(rows.fieldnames or ()):
            raise OcrFailure("OCR TSV is missing required columns")
        for row in rows:
            if row["level"] != "5" or not row["text"].strip():
                continue
            score = float(row["conf"])
            if not math.isfinite(score) or not 0 <= score <= 100:
                raise OcrFailure("OCR confidence is outside [0, 100]")
            if score < confidence:
                continue
            left, top, width, height = (int(row[key]) for key in ("left","top","width","height"))
            if left < 0 or top < 0 or width <= 0 or height <= 0:
                raise OcrFailure("OCR returned invalid bounding coordinates")
            x, y = left // scale, top // scale
            right, bottom = math.ceil((left+width)/scale), math.ceil((top+height)/scale)
            if size and (right > size[0] or bottom > size[1]):
                raise OcrFailure("OCR bounding box lies outside its input screenshot")
            line = tuple(int(row[key]) for key in ("page_num","block_num","par_num","line_num"))
            region = Region(origin[0]+x,origin[1]+y,right-x,bottom-y)
            word = TextBox(row["text"].strip(), score, region, line)
            words.append(word)
            lines.setdefault(line, []).append(word.text)
            if len(words) > 10000:
                raise OcrFailure("OCR word limit exceeded")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise OcrFailure("Malformed OCR TSV data") from error
    return TextResult("\n".join(" ".join(line) for line in lines.values()), tuple(words))


def search_text(result: TextResult, query: str, *, exact=True, case_sensitive=False):
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ValueError("Text query must be a nonempty string of at most 500 characters")
    if type(exact) is not bool or type(case_sensitive) is not bool:
        raise ValueError("exact and case_sensitive must be booleans")
    normalize = (lambda s: " ".join(s.split())) if case_sensitive else (lambda s: " ".join(s.split()).casefold())
    needle = normalize(query)
    length = len(query.split())
    groups = {}
    for word in result.words:
        groups.setdefault(word.line, []).append(word)
    matches = []
    for words in groups.values():
        for start in range(len(words)):
            batch = words[start:start+length]
            if len(batch) != length:
                continue
            text = " ".join(word.text for word in batch)
            candidate = normalize(text)
            if (candidate == needle if exact else needle in candidate):
                left,top = min(w.region.x for w in batch),min(w.region.y for w in batch)
                right = max(w.region.x+w.region.width for w in batch)
                bottom = max(w.region.y+w.region.height for w in batch)
                matches.append(TextBox(text, min(w.confidence for w in batch), Region(left,top,right-left,bottom-top), batch[0].line))
    return matches


class TesseractOCR:
    def __init__(self, executable=None):
        configured = executable or os.environ.get("STUDIO_TESSERACT") or "tesseract"
        self.executable = str(Path(configured).expanduser())

    def status(self):
        if shutil.which(self.executable) is None:
            raise OcrUnavailable("Tesseract is unavailable. Configure an existing tesseract/tesseract.exe in Settings → Recognition; provide eng.traineddata locally. Nothing is downloaded automatically.")
        outputs = []
        for arguments in (("--version",), ("--list-langs",)):
            try:
                result = subprocess.run([self.executable, *arguments], capture_output=True, timeout=5, check=False, shell=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise OcrUnavailable(f"Could not inspect configured Tesseract: {error}") from error
            if result.returncode:
                raise OcrUnavailable(result.stderr.decode(errors="replace")[:1000])
            outputs.append(result.stdout.decode(errors="replace")[:4000])
        return "\n".join(outputs)

    def recognize(self, frame, *, region=None, language="eng", confidence=0, timeout=10., psm=6,
                  preprocess="grayscale", checkpoint=None):
        _image("OCR screenshot", frame)
        if not isinstance(language, str) or len(language)>100 or re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*",language) is None:
            raise ValueError("Use installed Tesseract language identifiers such as eng or eng+fra")
        if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not 0 <= confidence <=100 or not math.isfinite(confidence):
            raise ValueError("OCR confidence must be in [0, 100]")
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0 < timeout <=60 or not math.isfinite(timeout):
            raise ValueError("OCR timeout must be positive seconds up to 60")
        if psm not in (3,6,7,11,12,13) or type(psm) is not int:
            raise ValueError("Supported OCR page modes are 3,6,7,11,12,13")
        if preprocess not in ("none","grayscale","threshold"):
            raise ValueError("OCR preprocessing must be none, grayscale or threshold")
        h,w = frame.shape[:2]
        region = Region(0,0,w,h) if region is None else region
        if not isinstance(region,Region) or region.x+region.width>w or region.y+region.height>h:
            raise ValueError("OCR search region lies outside the screenshot")
        if region.width*region.height > 4_000_000:
            raise ValueError("OCR is limited to 4 megapixels; select a smaller Region")
        if shutil.which(self.executable) is None:
            raise OcrUnavailable("Tesseract is not installed/configured. Select tesseract.exe/tesseract in Settings → Recognition and supply local language data; no automatic downloads are performed.")
        check = checkpoint or (lambda: None)
        check()
        deadline = time.monotonic()+timeout
        pixels=frame[region.y:region.y+region.height,region.x:region.x+region.width]
        scale = 2 if region.width*region.height <=1_000_000 else 1
        if scale==2:
            pixels=cv2.resize(pixels,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
        if preprocess != "none":
            pixels=cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
            if preprocess=="threshold":
                _,pixels=cv2.threshold(pixels,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        else:
            pixels=cv2.cvtColor(pixels,cv2.COLOR_RGB2BGR)
        ok,encoded=cv2.imencode('.png',pixels)
        if not ok:
            raise OcrFailure("Could not encode OCR pixels")
        arguments=[self.executable,"stdin","stdout","-l",language,"--psm",str(psm),"tsv"]
        process=None
        try:
            check()
            process=subprocess.Popen(arguments,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     shell=False,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            first=True
            while True:
                check()
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise TimeoutError("OCR recognition deadline expired")
                try:
                    output,error=process.communicate(encoded.tobytes() if first else None,timeout=min(.1,remaining))
                    break
                except subprocess.TimeoutExpired:
                    first=False
            if process.returncode:
                detail=error.decode(errors="replace")[:2000]
                if "traineddata" in detail or "Failed loading language" in detail:
                    raise OcrUnavailable("Required OCR language data is missing. Configure TESSDATA_PREFIX or install the requested local traineddata. " + detail)
                raise OcrFailure("Tesseract failed: "+detail)
            check()
            if time.monotonic()>deadline:
                raise TimeoutError("OCR recognition exceeded its deadline")
            return parse_tsv(output.decode("utf-8",errors="replace"),scale=scale,origin=(region.x,region.y),size=(region.width,region.height),confidence=confidence)
        except TimeoutError:
            raise
        except OSError as error:
            raise OcrUnavailable(f"Could not execute Tesseract: {error}") from error
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=2)
