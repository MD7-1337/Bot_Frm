"""Best-effort parent-process metrics, never invented total-host/worker usage."""
from __future__ import annotations

import os
import sys
import time


def resident_bytes():
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            *[(name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]]
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        elif sys.platform.startswith("linux"):
            with open("/proc/self/statm", encoding="ascii") as stream:
                return int(stream.read(200).split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    return None


class HostMetrics:
    def __init__(self):
        self.previous = None

    def sample(self):
        now = time.monotonic()
        cpu = os.times()
        seconds = cpu.user + cpu.system
        percent = None
        if self.previous is not None and now > self.previous[0]:
            percent = max(0., 100 * (seconds - self.previous[1]) / (now - self.previous[0]))
        self.previous = now, seconds
        return {"cpu_percent": percent, "resident_bytes": resident_bytes()}
