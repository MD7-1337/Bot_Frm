"""Connection snapshots with stable identities and stale-operation generations.

Only a successful discovery result establishes that a previously observed serial
is absent. A failed discovery must call mark_unknown(), never update([]).
The registry does not auto-reconnect or replay any device actions.
"""
from __future__ import annotations

from dataclasses import replace
import threading

from app.devices.adb import DeviceInfo, validate_observed_serial


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: dict[str, DeviceInfo] = {}
        self._lock = threading.Lock()

    def update(self, devices: list[DeviceInfo]) -> list[DeviceInfo]:
        incoming: dict[str, DeviceInfo] = {}
        for device in devices:
            if not isinstance(device, DeviceInfo):
                raise ValueError("Device snapshots must contain DeviceInfo records")
            validate_observed_serial(device.serial)
            if set(device.serial) == {"?"} and device.available:
                raise ValueError("An unreadable USB serial cannot be an available device")
            if device.serial in incoming:
                raise ValueError("Duplicate device serial in discovery result")
            incoming[device.serial] = device
        with self._lock:
            for serial, previous in tuple(self._devices.items()):
                if serial not in incoming:
                    self._devices[serial] = self._transition(previous, "disconnected", previous.model)
            for serial, device in incoming.items():
                previous = self._devices.get(serial)
                if previous is None:
                    self._devices[serial] = replace(device, generation=1)
                else:
                    self._devices[serial] = self._transition(previous, device.state, device.model or previous.model)
            return list(self._devices.values())

    @staticmethod
    def _transition(previous: DeviceInfo, state: str, model: str | None) -> DeviceInfo:
        return DeviceInfo(previous.serial, state, model,
                          previous.generation + int(previous.state != state))

    def mark_unknown(self) -> list[DeviceInfo]:
        """Invalidate availability after failed discovery without claiming absence."""
        with self._lock:
            for serial, previous in tuple(self._devices.items()):
                self._devices[serial] = self._transition(previous, "unknown", previous.model)
            return list(self._devices.values())

    def snapshot(self) -> list[DeviceInfo]:
        with self._lock:
            return list(self._devices.values())

    def get(self, serial: str) -> DeviceInfo | None:
        with self._lock:
            return self._devices.get(serial)
