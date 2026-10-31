"""Short reproducible fixture measurements, not Android/Windows performance claims."""
from pathlib import Path
import json
import platform
import shutil
import statistics
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
from app.simulation.model import SimulationManager
from app.simulation.transport import SimulationTransport
from app.vision.matching import find_scaled, Region
from app.vision.color import find_color
from app.vision.ocr import TesseractOCR
from app.host_metrics import HostMetrics


def measure(operation,count):
    values=[]
    for _ in range(count):
        started=time.perf_counter();operation();values.append(1000*(time.perf_counter()-started))
    return {'samples':count,'median_ms':round(statistics.median(values),2),'max_ms':round(max(values),2)}


def main():
    manager=SimulationManager()
    try:
        devices=[manager.create() for _ in range(4)]
        clients=[manager.client(info.serial) for info in devices]
        frame=clients[0].capture()
        template=frame[480:544,60:300].copy()
        result={'environment':platform.platform(),'python':platform.python_version(),'source':'stateful simulation, 360x720 RGB, no Android hardware',
                'render_and_database':measure(clients[0].capture,50),
                'png_capture':measure(SimulationTransport(clients[0]).frame,30),
                'four_captures_sequential':measure(lambda:[client.capture() for client in clients],20),
                'rgb_template_fullscreen':measure(lambda:find_scaled(frame,template),30),
                'rgb_template_region':measure(lambda:find_scaled(frame,template,region=Region(40,450,280,140)),30),
                'color_first_100':measure(lambda:find_color(frame,(105,165,255),0,limit=100),30)}
        if shutil.which('tesseract'):
            result['tesseract_button_region']=measure(lambda:TesseractOCR().recognize(frame,region=Region(60,480,240,64)),5)
        else:result['tesseract_button_region']='unavailable; not installed automatically'
        result['parent_metrics']=HostMetrics().sample()
        print(json.dumps(result,indent=2))
    finally:manager.close()


if __name__=='__main__':main()
