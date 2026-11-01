"""Typed failure advice and explicitly bounded retries of device *reads*.

Recovery never reconnects a device, restarts a script or repeats input. The
read-only allowlist is intentional: ``click`` can fail after its tap took effect.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
import json
import math
import time
from typing import Callable

from app.automation.api import errors


def classify_failure(error: BaseException) -> dict:
    """Bounded, JSON-safe advice based on actual exception types, not message guesses.

    Transport acknowledgment/timeouts cannot establish whether input took effect.
    Every restart remains explicit, with a fresh device lease and trust approval.
    """
    rules = (
        ((errors.DeviceUnauthorized, errors.DeviceOffline, errors.DeviceDisconnected),
         'device_connection', 'Inspect Device Manager or reset the demo, verify the screen, then explicitly restart. Never replay pending input after reconnection.'),
        ((errors.CommandTimeout, errors.CommandFailed),
         'input_outcome_unknown', 'Inspect the current screen before restarting; a command may already have taken effect. No automatic retry is safe by default.'),
        ((errors.RecognitionTimeout, errors.ImageNotFound, errors.AmbiguousMatch),
         'recognition', 'Capture a fresh screen in Visual Tools; inspect the target, Region, score and appearance timing before restarting.'),
        ((errors.FrameUnavailable,),
         'frame_capture', 'Inspect the current device connection and screen capture diagnostics. Only explicitly bounded read-only recovery may retry a fresh screenshot; input is never replayed.'),
        ((errors.AssetNotFound, errors.InvalidAsset),
         'image_asset', 'Check this project\'s image library and saved target reference. Choose a textured crop inside the project.'),
        ((errors.OCRUnavailable,),
         'ocr_dependency', 'Configure a local Tesseract executable and requested language data in Settings → Recognition. No model is downloaded automatically.'),
        ((errors.OCRFailed,),
         'ocr_engine', 'Inspect the OCR error, language and search region. Test the frozen capture in Recognition Inspector.'),
        ((errors.InvalidCoordinates, errors.CrossDeviceTarget),
         'target_geometry', 'Inspect original screen coordinates, orientation and device ownership. Capture fresh targets after resolution changes.'),
        ((errors.UnsupportedCapability,),
         'unsupported', 'Check the selected backend capabilities. Simulation cannot launch Android packages.'),
    )
    for classes, category, advice in rules:
        if isinstance(error, classes):
            break
    else:
        category, advice = 'python', 'Inspect the traceback and failed source line. Edit the script and explicitly restart when ready.'
    return {'category': category, 'advice': advice, 'automatic_retry': False}


def _seconds(value, name, *, positive=False, maximum=86400):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0 <= value <= maximum or not math.isfinite(value)
            or (positive and value == 0)):
        raise ValueError(f"{name} must be finite {'positive' if positive else 'nonnegative'} seconds <= {maximum}")
    return float(value)


@dataclass(frozen=True)
class RetryPolicy:
    """At most ten total attempts, including the first; defaults to no retry.

    The deadline includes read and backoff time. An in-flight native operation
    retains its existing transport deadline; this cannot unwind a native call.
    """

    max_attempts: int = 1
    initial_delay: float = .1
    multiplier: float = 2.
    max_delay: float = 2.
    budget: float = 10.

    def __post_init__(self):
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be an integer from 1 to 10")
        _seconds(self.initial_delay, "initial_delay", maximum=60)
        _seconds(self.max_delay, "max_delay", maximum=60)
        _seconds(self.budget, "budget", positive=True)
        if (isinstance(self.multiplier, bool) or not isinstance(self.multiplier, (int, float))
                or not 1 <= self.multiplier <= 10 or not math.isfinite(self.multiplier)):
            raise ValueError("multiplier must be finite from 1 to 10")

    def delay_after(self, attempt: int) -> float:
        if type(attempt) is not int or not 1 <= attempt <= self.max_attempts:
            raise ValueError("attempt is outside this policy")
        return min(self.max_delay, self.initial_delay * self.multiplier ** (attempt - 1))


@dataclass(frozen=True)
class RecoverySession:
    """Exact device generation and source snapshot; never a reconnect permit."""

    serial: str
    generation: int
    source_hash: str

    def __post_init__(self):
        from app.devices.adb import validate_serial
        from app.simulation.model import is_simulation, validate_identity
        (validate_identity if is_simulation(self.serial) else validate_serial)(self.serial)
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("A positive connection generation is required")
        if (not isinstance(self.source_hash, str) or len(self.source_hash) != 64
                or any(c not in "0123456789abcdef" for c in self.source_hash)):
            raise ValueError("source_hash must be a SHA-256 hexadecimal digest")

    @classmethod
    def for_source(cls, serial, generation, source):
        if not isinstance(source, str) or len(source.encode("utf-8")) > 1_048_576:
            raise ValueError("Source must be text of at most 1 MiB")
        return cls(serial, generation, hashlib.sha256(source.encode("utf-8")).hexdigest())


@dataclass(frozen=True)
class RecoveryCheckpoint:
    """Bounded JSON progress marker, verified against its original session.

    It records progress only. Resuming Python or restarting a task still needs
    an explicit trusted run and a fresh device lease from the normal runtime.
    """

    session: RecoverySession
    name: str
    payload_json: str

    def __post_init__(self):
        if not isinstance(self.session, RecoverySession):
            raise ValueError("A checkpoint requires its exact recovery session")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 200:
            raise ValueError("Checkpoint name must contain 1–200 characters")
        if not isinstance(self.payload_json, str) or len(self.payload_json.encode("utf-8")) > 16_384:
            raise ValueError("Checkpoint data exceeds 16 KiB")
        try:
            json.loads(self.payload_json, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite checkpoint value")))
        except (json.JSONDecodeError, RecursionError) as error:
            raise ValueError("Checkpoint data must be valid finite JSON") from error

    @property
    def data(self):
        return json.loads(self.payload_json)


READ_METHODS = frozenset({
    "capture", "getResolution", "getPixel", "findColor", "find", "findAll",
    "exists", "waitImage", "waitVanish", "recognizeText", "readText",
    "findText", "textExists", "waitText",
})
_RETRYABLE = (errors.ImageNotFound, errors.RecognitionTimeout, errors.FrameUnavailable)


class RecoveryBudgetExceeded(errors.RecognitionTimeout):
    """The configured total read-recovery budget expired."""


class RecoveryEngine:
    """Retry built-in read methods without accepting arbitrary action callbacks.

    Uses the assigned Device's normal pause/cancellation safe points and wait.
    Trusted user Python can bypass this API; process isolation is not a sandbox.
    A context supplied by an application host must include ``current_session``
    so edits, disconnects and generation changes invalidate checkpoints/retries.
    """

    def __init__(self, device, policy=None, *, session=None, current_session=None,
                 on_event: Callable[[dict], None] | None = None):
        from app.automation.api.device import Device
        if not isinstance(device, Device):
            raise TypeError("Recovery requires the assigned Device")
        self.device = device
        self.policy = policy if policy is not None else RetryPolicy()
        if not isinstance(self.policy, RetryPolicy):
            raise TypeError("policy must be a RetryPolicy")
        if session is not None and (not isinstance(session, RecoverySession)
                                    or session.serial != device.serial or not callable(current_session)):
            raise ValueError("Recovery session must match the device and have a current-session validator")
        if session is None and current_session is not None:
            raise ValueError("current_session requires an explicit recovery session")
        self.session = session
        self.current_session = current_session
        self.on_event = on_event or (lambda event: None)

    def _check(self):
        self.device._check()
        if self.session is not None and self.current_session() != self.session:
            raise errors.DeviceDisconnected("Recovery session is obsolete; explicitly authorize a new run")

    def checkpoint(self, name: str, data=None) -> RecoveryCheckpoint:
        self._check()
        if self.session is None:
            raise ValueError("Checkpoints require an explicit device generation and source snapshot")
        try:
            payload = json.dumps(data, allow_nan=False, ensure_ascii=True)
        except (ValueError, TypeError, RecursionError) as error:
            raise ValueError("Checkpoint data must be finite JSON") from error
        return RecoveryCheckpoint(self.session, name, payload)

    def verify_checkpoint(self, checkpoint: RecoveryCheckpoint):
        self._check()
        if not isinstance(checkpoint, RecoveryCheckpoint) or checkpoint.session != self.session:
            raise errors.DeviceDisconnected("Checkpoint belongs to another source or device connection")
        return checkpoint.data

    def read(self, method: str, *args, **kwargs):
        """Execute a built-in read, retrying only typed transient recognition errors.

        Transport failures, missing assets, ambiguous targets, OCR dependencies,
        arbitrary Python errors and cancellation propagate immediately. A valid
        ``exists``/``textExists`` false result is a successful read, not failure.
        """
        from app.automation.api.device import Device
        if not isinstance(method, str) or method not in READ_METHODS:
            raise ValueError("Recovery permits only read-only Device methods; input and arbitrary callbacks are forbidden")
        # Resolve the built-in class method, not a possibly replaced instance
        # attribute. Binding also validates arguments before the first attempt.
        operation = getattr(Device, method)
        signature = inspect.signature(operation)
        bound = signature.bind(self.device, *args, **kwargs)
        started = time.monotonic()
        deadline = started + self.policy.budget
        for attempt in range(1, self.policy.max_attempts + 1):
            self._check()
            # Subtraction of a rounded absolute deadline can exceed the original
            # budget by an ulp on a coarse clock. Never grant more than policy.
            remaining = min(self.policy.budget, deadline - time.monotonic())
            if remaining <= 0:
                raise RecoveryBudgetExceeded("Read recovery time budget expired")
            current = dict(bound.arguments)
            # Clamp waits to the remaining total budget, including positional
            # timeout arguments and the method's default timeout when omitted.
            if "timeout" in signature.parameters:
                timeout = current.get("timeout", signature.parameters["timeout"].default)
                if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
                    current["timeout"] = min(timeout, remaining)
            invocation = signature.bind_partial(**current)
            try:
                result = operation(*invocation.args, **invocation.kwargs)
                self._check()
                if time.monotonic() > deadline:
                    raise RecoveryBudgetExceeded("Read finished after the recovery time budget")
                return result
            except _RETRYABLE as error:
                if isinstance(error, RecoveryBudgetExceeded) or attempt == self.policy.max_attempts:
                    raise
                self._check()
                remaining = deadline - time.monotonic()
                delay = self.policy.delay_after(attempt)
                if remaining <= delay:
                    raise RecoveryBudgetExceeded("No time remains for another read attempt") from error
                self.on_event({"event": "recovery_retry", "serial": self.device.serial,
                               "method": method, "attempt": attempt,
                               "next_attempt": attempt + 1, "delay": delay,
                               "error_type": type(error).__name__})
                self.device.sleep(delay)
        raise AssertionError("Unreachable retry state")
