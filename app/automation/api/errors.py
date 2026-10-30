"""Catchable automation failures; none silently imply an action was replayed."""


class AutomationError(Exception):
    """Base class for built-in automation failures."""


class NoExecutionContext(AutomationError, RuntimeError):
    """A simple API function was called without an assigned script device."""


class AssetNotFound(AutomationError, FileNotFoundError):
    """An image reference does not exist in the configured image library."""


class InvalidAsset(AutomationError, ValueError):
    """An image is unsafe to resolve, malformed, unsupported or degenerate."""


class InvalidCoordinates(AutomationError, ValueError):
    """Coordinates or a search region lie outside the current device screen."""


class CrossDeviceTarget(AutomationError, ValueError):
    """A recognition match belongs to another device's execution context."""


class ImageNotFound(AutomationError, LookupError):
    """A valid capture/search produced no match above the requested score."""


class AmbiguousMatch(AutomationError):
    """A single-target operation found multiple distinct qualifying matches."""


class RecognitionTimeout(AutomationError, TimeoutError):
    """A bounded image appearance/disappearance wait exceeded its deadline."""


class FrameUnavailable(AutomationError):
    """The device did not supply a usable full-resolution RGB screenshot."""


class DeviceDisconnected(AutomationError):
    """The assigned device is absent or its transport closed."""


class DeviceUnauthorized(DeviceDisconnected):
    """The assigned device has not authorized debugging access."""


class DeviceOffline(DeviceDisconnected):
    """The assigned device's ADB transport is offline."""


class CommandTimeout(AutomationError, TimeoutError):
    """A transport deadline expired; a sent action's outcome can be unknown."""


class CommandFailed(AutomationError):
    """An Android command failed without evidence that replay is safe."""


class UnsupportedCapability(AutomationError):
    """The requested feature/input cannot be represented by this backend."""


class OCRUnavailable(UnsupportedCapability):
    """Configure a local OCR executable/language model; no model is auto-downloaded."""


class OCRFailed(AutomationError):
    """OCR execution or output failed, distinct from legitimate text absence."""


class Cancelled(AutomationError):
    """The execution context cancelled before or during an API safe point."""
