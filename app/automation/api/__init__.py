"""Public SikuliX-style API. Functions operate only within a bound Device context."""
from app.automation.api.device import API_METHOD_NAMES, Device, Target
from app.automation.api.models import Location, Match, Offset, Pattern, Region, Screen, TextMatch, OCRResult
from app.automation.api.errors import (
    AmbiguousMatch, AssetNotFound, AutomationError, Cancelled, CommandFailed,
    CommandTimeout, CrossDeviceTarget, DeviceDisconnected, DeviceOffline,
    DeviceUnauthorized, FrameUnavailable, ImageNotFound, InvalidAsset,
    InvalidCoordinates, NoExecutionContext, RecognitionTimeout, UnsupportedCapability, OCRUnavailable, OCRFailed,
)
from app.automation.api.context import get_current_device, use_device
from app.automation.api import context as _context

for _name in API_METHOD_NAMES:
    globals()[_name] = getattr(_context, _name)

__all__ = [*API_METHOD_NAMES, "API_METHOD_NAMES", "Device", "Target", "Location", "Region",
           "Pattern", "Offset", "Match", "Screen", "TextMatch", "OCRResult", "OCRUnavailable", "OCRFailed", "get_current_device", "use_device",
           "AutomationError", "NoExecutionContext", "AssetNotFound", "InvalidAsset",
           "InvalidCoordinates", "CrossDeviceTarget", "ImageNotFound", "AmbiguousMatch",
           "RecognitionTimeout", "FrameUnavailable", "DeviceDisconnected", "DeviceOffline",
           "DeviceUnauthorized", "CommandTimeout", "CommandFailed", "UnsupportedCapability", "Cancelled"]
