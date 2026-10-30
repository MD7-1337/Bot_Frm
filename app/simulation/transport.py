"""GUI adapter for a selected simulation; wrong serials fail before dispatch."""
import time

import cv2

from app.simulation.model import LABEL
from app.streaming.capture import ScreenFrame


class SimulationTransport:
    def __init__(self, client):
        self.client = client

    def _check(self, serial):
        if serial != self.client.serial:
            raise ValueError("Simulation transport is bound to another session")

    def screenshot(self, serial):
        self._check(serial)
        image = self.client.capture()
        ok, encoded = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        if not ok:
            raise RuntimeError("Could not encode simulated pixels")
        return encoded.tobytes()

    def frame(self):
        payload = self.screenshot(self.client.serial)
        return ScreenFrame(self.client.serial, payload, 360, 720, time.monotonic(), "simulation")

    def tap(self, serial, x, y):
        self._check(serial)
        self.client.tap(x,y)

    def swipe(self, serial, x1,y1,x2,y2,duration_ms=500):
        self._check(serial)
        self.client.swipe(x1,y1,x2,y2,duration_ms)

    def key(self, serial, key):
        self._check(serial)
        self.client.key(key)
