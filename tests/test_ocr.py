"""Actual optional Tesseract plus deterministic parsing/error contracts."""
import shutil
import threading
import time
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from app.automation.api import Device, Region, CrossDeviceTarget, OCRUnavailable, RecognitionTimeout
from app.automation.api.models import TextMatch
from app.projects.library import AssetLibrary
from app.vision.ocr import TesseractOCR, OcrUnavailable, OcrFailure, parse_tsv, search_text

HEADER='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
TSV=HEADER+'5\t1\t1\t1\t1\t1\t20\t40\t80\t20\t95.5\tSTART\n'+'5\t1\t1\t1\t1\t2\t110\t40\t120\t20\t91\tCONTINUE\n'


def text_image():
    frame=np.full((180,700,3),255,np.uint8)
    cv2.putText(frame,'START CONTINUE',(25,105),cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),3,cv2.LINE_AA)
    return frame


def test_tsv_confidence_region_scale_and_phrase_contract():
    result=parse_tsv(TSV,scale=2,origin=(10,20),size=(200,100),confidence=50)
    assert result.text=='START CONTINUE'
    assert result.words[0].region==Region(20,40,40,10)
    assert result.words[0].confidence==95.5
    assert len(search_text(result,'start continue'))==1
    assert search_text(result,'STAR')==[]
    assert len(search_text(result,'STAR',exact=False))==1
    assert search_text(result,'start',case_sensitive=True)==[]
    assert parse_tsv(HEADER).text==''
    assert parse_tsv(TSV,confidence=96).words==()


@pytest.mark.parametrize('payload',['garbage',HEADER.replace('conf','bad'),TSV.replace('95.5','nan'),TSV.replace('95.5','101'),TSV.replace('\t20\t40\t80','\t-1\t40\t80')])
def test_bad_output_is_not_no_text(payload):
    with pytest.raises(OcrFailure):
        parse_tsv(payload)


def test_missing_engine_is_explicit_and_never_downloads(monkeypatch):
    monkeypatch.setattr('app.vision.ocr.shutil.which',lambda path:None)
    launch=Mock()
    monkeypatch.setattr('app.vision.ocr.subprocess.Popen',launch)
    with pytest.raises(OcrUnavailable,match='not installed/configured'):
        TesseractOCR('missing-engine').recognize(text_image())
    launch.assert_not_called()


@pytest.mark.parametrize('kwargs',[{'language':'../eng'},{'language':'eng;echo'},{'confidence':-1},{'confidence':101},{'confidence':10**400},{'timeout':10**400},{'timeout':0},{'timeout':float('nan')},{'psm':True},{'region':Region(600,0,200,100)},{'preprocess':'magic'}])
def test_invalid_ocr_options(kwargs):
    with pytest.raises(ValueError):
        TesseractOCR().recognize(text_image(),**kwargs)


@pytest.mark.skipif(shutil.which('tesseract') is None,reason='Optional actual Tesseract executable unavailable; no model download')
def test_actual_tesseract_extracts_text_boxes_and_region_pixels():
    frame=text_image()
    before=frame.copy()
    result=TesseractOCR().recognize(frame)
    assert 'START' in result.text and 'CONTINUE' in result.text
    start=search_text(result,'START')[0]
    assert start.confidence>70
    assert 20<=start.region.x<=40 and 50<=start.region.y<=80
    crop=TesseractOCR().recognize(frame,region=Region(230,30,380,100))
    assert 'CONTINUE' in crop.text and 'START' not in crop.text
    assert all(w.region.x>=230 and w.region.y>=30 for w in crop.words)
    np.testing.assert_array_equal(frame,before)


@pytest.mark.skipif(shutil.which('tesseract') is None,reason='Optional Tesseract unavailable')
def test_actual_api_read_search_wait_and_device_ownership(tmp_path):
    class Backend:
        serial='ocr-fixture'
        def capture(self): return text_image()
        def tap(self,x,y): self.tap_point=(x,y)
    backend=Backend(); device=Device(backend,AssetLibrary(tmp_path))
    assert 'START' in device.readText()
    assert device.textExists('CONTINUE')
    assert device.textExists('STAR',exact=False)
    assert not device.textExists('ABSENT')
    match=device.waitText('START',timeout=2)
    assert isinstance(match,TextMatch) and match.device_serial=='ocr-fixture'
    assert device.click(match)==match.target
    foreign=TextMatch(match.text,match.confidence,match.region,'other',match.source_size,match.frame_id)
    with pytest.raises(CrossDeviceTarget): device.click(foreign)
    with pytest.raises(RecognitionTimeout): device.waitText('ABSENT',timeout=.05)


@pytest.mark.skipif(shutil.which('tesseract') is None,reason='Optional Tesseract unavailable')
def test_native_ocr_child_is_reaped_on_cancellation(monkeypatch):
    from app.automation.api import Cancelled
    real_popen=__import__('subprocess').Popen
    children=[]
    def launch(*args,**kwargs):
        process=real_popen(*args,**kwargs); children.append(process); return process
    monkeypatch.setattr('app.vision.ocr.subprocess.Popen',launch)
    calls=[]
    def check():
        calls.append(True)
        if children: raise Cancelled('expected cancellation')
    with pytest.raises(Cancelled):
        TesseractOCR().recognize(text_image(),checkpoint=check)
    assert children and all(process.poll() is not None for process in children)
