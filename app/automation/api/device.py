"""One implementation for bound Device methods and simple script functions."""
from __future__ import annotations

from collections.abc import Callable
import math
from pathlib import Path
import time
from typing import Any, Protocol

import cv2
import numpy as np

from app.automation.api import errors
from app.automation.api.models import Location, Match, Offset, Pattern, Region, Screen, TextMatch, OCRResult
from app.vision.matching import find_scaled
from app.vision.color import pixel, find_color

API_METHOD_NAMES = (
    "click", "doubleClick", "longPress", "tap", "swipe", "drag", "scroll",
    "find", "findAll", "exists", "waitImage", "waitVanish", "sleep", "wait",
    "back", "home", "launchApp", "stopApp", "typeText", "capture",
    "getResolution", "getDevice", "getPixel", "findColor",
    "recognizeText", "readText", "findText", "textExists", "waitText",
)
Target = Location | Match | TextMatch | Pattern | str | tuple[int, int]


class Backend(Protocol):
    serial: str

    def capture(self) -> np.ndarray: ...
    def tap(self, x: int, y: int) -> None: ...
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None: ...
    def key(self, key: str) -> None: ...
    def launch_app(self, package: str) -> None: ...
    def stop_app(self, package: str) -> None: ...
    def type_text(self, text: str) -> None: ...


class ImageLibrary(Protocol):
    def resolve(self, reference: str) -> Path: ...


def seconds(value: float, name: str, *, positive: bool = False, maximum: float = 86400) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number of seconds")
    try:
        valid = math.isfinite(value) and 0 <= value <= maximum and (not positive or value > 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be finite seconds in {'(0' if positive else '[0'}, {maximum}]")
    return float(value)


class Device:
    """One serial-bound automation context; never selects an ADB default phone.

    backend owns transport deadlines. Recognition waits use monotonic wall-clock
    deadlines, including time spent paused and capturing. timeout=0 permits one
    immediate capture/search. A running transport call is not forcibly rewound.
    checkpoint and interruptible_wait implement worker cancellation/pause.
    """

    def __init__(self, backend: Backend, assets: ImageLibrary, *,
                 checkpoint: Callable[[], None] | None = None,
                 interruptible_wait: Callable[[float], None] | None = None,
                 emit: Callable[..., None] | None = None, ocr=None):
        if not isinstance(backend.serial, str) or not backend.serial:
            raise ValueError("Device backend requires its explicit serial")
        self._backend = backend
        self._serial = backend.serial
        self._assets = assets
        self._checkpoint = checkpoint or (lambda: None)
        self._interruptible_wait = interruptible_wait
        self._emit = emit or (lambda *args, **kwargs: None)
        self._ocr = ocr

    @property
    def serial(self) -> str:
        return self._serial

    def _check(self):
        self._checkpoint()
        if self._backend.serial != self._serial:
            raise errors.CrossDeviceTarget("The bound backend identity changed")

    def bindings(self) -> dict[str, Any]:
        """Bindings for one execution namespace; imported functions use contextvars."""
        bindings = {name: getattr(self, name) for name in API_METHOD_NAMES}
        bindings.update(device=self, Pattern=Pattern, Offset=Offset, Location=Location,
                        Region=Region, Match=Match, Screen=Screen, TextMatch=TextMatch, OCRResult=OCRResult)
        for name in dir(errors):
            value = getattr(errors, name)
            if isinstance(value, type) and issubclass(value, errors.AutomationError):
                bindings[name] = value
        return bindings

    def _action(self, command: str, operation: Callable[[], None], **arguments):
        self._check()
        operation()
        self._emit("action", command=command, arguments=arguments)
        self._check()

    def capture(self) -> Screen:
        """Capture one full-resolution immutable RGB Screen; transport failures propagate."""
        self._check()
        image = self._backend.capture()
        self._check()
        try:
            return Screen.from_array(self.serial, image)
        except ValueError as error:
            raise errors.FrameUnavailable(str(error)) from error

    def getResolution(self) -> tuple[int, int]:
        """Return current full capture width/height; never a scaled preview size."""
        return self.capture().resolution

    def getDevice(self) -> str:
        """Return this execution's assigned serial string (compatible with Phase 0)."""
        self._check()
        return self.serial

    def getPixel(self, x: int, y: int) -> tuple[int, int, int]:
        """Fresh RGB pixel; original Android coordinates. No input is sent."""
        screen = self.capture()
        self._coordinates(x, y, screen.resolution)
        return pixel(screen.to_numpy(), x, y)

    def findColor(self, color: tuple[int, int, int], tolerance: int = 0, *, region: Region | None = None, limit: int = 100) -> list[Location]:
        """Fresh screenshot; row-major pixel locations, inclusive per-channel RGB tolerance 0–255.

        Color channels are integers 0–255, limit is 1–10000, and search bounds
        use original Android pixels. Results are pixels, not clustered objects.
        A legitimate absence returns []; invalid values raise ValueError.
        """
        screen = self.capture()
        self._region(region, screen)
        self._check()
        found = find_color(screen.to_numpy(), color, tolerance, region, limit)
        self._check()
        return found

    @staticmethod
    def _coordinates(x: int, y: int, size: tuple[int, int]) -> Location:
        if type(x) is not int or type(y) is not int or not (0 <= x < size[0] and 0 <= y < size[1]):
            raise errors.InvalidCoordinates(f"Coordinates must be integer pixels within {size[0]}×{size[1]}")
        return Location(x, y)

    def tap(self, x: int, y: int) -> None:
        """Tap current Android integer coordinates; out-of-bounds values never dispatch."""
        point = self._coordinates(x, y, self.getResolution())
        self._tap(point)

    def _tap(self, point: Location):
        self._action("tap", lambda: self._backend.tap(point.x, point.y), x=point.x, y=point.y)

    def _resolved_target(self, target: Target) -> tuple[Location, tuple[int, int]]:
        if isinstance(target, (str, Pattern)):
            target = self.find(target)
        if isinstance(target, (Match, TextMatch)):
            if target.device_serial != self.serial:
                raise errors.CrossDeviceTarget("Match belongs to another device")
            size = self.getResolution()
            if target.source_size != size:
                raise errors.InvalidCoordinates("Device resolution changed after this match; find the target again")
            point = target.target
            return self._coordinates(point.x, point.y, size), size
        if isinstance(target, Location):
            size = self.getResolution()
            return self._coordinates(target.x, target.y, size), size
        if isinstance(target, tuple) and len(target) == 2:
            size = self.getResolution()
            return self._coordinates(target[0], target[1], size), size
        raise TypeError("Target must be an image reference, Pattern, Match, Location or (x, y) tuple")

    def _target(self, target: Target) -> Location:
        return self._resolved_target(target)[0]

    def click(self, target: Target) -> Location:
        """Resolve one unambiguous target, tap it once and return its Android Location."""
        point = self._target(target)
        self._tap(point)
        return point

    def doubleClick(self, target: Target, interval: float = 0.1) -> Location:
        """Resolve once and send two taps, with cancellable finite interval ≤1 second."""
        interval = seconds(interval, "interval", maximum=1)
        point, source_size = self._resolved_target(target)
        self._tap(point)
        self.sleep(interval)
        if self.getResolution() != source_size:
            raise errors.InvalidCoordinates("Device resolution changed between double-click taps")
        self._tap(point)
        return point

    def longPress(self, target: Target, duration: float = 2.0) -> Location:
        """Hold a resolved location via a stationary swipe for 0<duration≤60 seconds."""
        duration = seconds(duration, "duration", positive=True, maximum=60)
        point = self._target(target)
        self._swipe(point, point, duration)
        return point

    def _swipe(self, first: Location, last: Location, duration: float):
        milliseconds = max(1, round(duration * 1000))
        arguments = dict(x1=first.x, y1=first.y, x2=last.x, y2=last.y, duration_ms=milliseconds)
        self._action("swipe", lambda: self._backend.swipe(**arguments), **arguments)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> None:
        """Press/move/release on this phone; finite duration is 0<seconds≤60."""
        duration = seconds(duration, "duration", positive=True, maximum=60)
        size = self.getResolution()
        self._swipe(self._coordinates(x1, y1, size), self._coordinates(x2, y2, size), duration)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 1.0) -> None:
        """ADB drag uses the supported endpoint swipe, not a raw continuous touch path."""
        self.swipe(x1, y1, x2, y2, duration)

    def scroll(self, direction: str, amount: int = 3) -> None:
        """Send 1–100 directional screen gestures; app scrolling support may vary."""
        if direction not in ("up", "down", "left", "right"):
            raise ValueError("direction must be up, down, left or right")
        if type(amount) is not int or not 1 <= amount <= 100:
            raise ValueError("amount must be an integer in [1, 100]")
        width, height = self.getResolution()
        if width < 4 or height < 4:
            raise errors.UnsupportedCapability("Screen is too small for a directional swipe")
        cx, cy = width // 2, height // 2
        # Direction describes finger motion, avoiding inferred app semantics.
        points = {"up": (cx, height * 3 // 4, cx, height // 4),
                  "down": (cx, height // 4, cx, height * 3 // 4),
                  "left": (width * 3 // 4, cy, width // 4, cy),
                  "right": (width // 4, cy, width * 3 // 4, cy)}
        for _ in range(amount):
            self.swipe(*points[direction], duration=0.35)

    def _pattern(self, image: str | Pattern) -> Pattern:
        if isinstance(image, str):
            return Pattern(image)
        if not isinstance(image, Pattern):
            raise TypeError("Image target must be a library reference or Pattern")
        return image

    def _template(self, pattern: Pattern) -> np.ndarray:
        self._check()
        try:
            path = self._assets.resolve(pattern.path)
            with Path(path).open("rb") as source:
                payload = source.read(16 * 1024 * 1024 + 1)
        except FileNotFoundError as error:
            raise errors.AssetNotFound(f"Image not found: {pattern.path}") from error
        except (ValueError, OSError) as error:
            raise errors.InvalidAsset(f"Cannot use image {pattern.path!r}: {error}") from error
        if len(payload) > 16 * 1024 * 1024:
            raise errors.InvalidAsset("Template file exceeds 16 MiB")
        try:
            image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
        except cv2.error as error:
            raise errors.InvalidAsset(f"Invalid image: {pattern.path}") from error
        if image is None or image.size == 0 or image.shape[0] * image.shape[1] > 16_777_216:
            raise errors.InvalidAsset(f"Invalid or oversized image: {pattern.path}")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _region(region: Region | None, screen: Screen) -> None:
        if region is not None and (not isinstance(region, Region)
                or region.x + region.width > screen.width or region.y + region.height > screen.height):
            raise errors.InvalidCoordinates("Search region must lie wholly inside the current screenshot")

    def findAll(self, image: str | Pattern, *, region: Region | None = None, limit: int = 100) -> list[Match]:
        """One capture/search; return score-descending distinct matches, maximum 1–10000."""
        if type(limit) is not int or not 1 <= limit <= 10_000:
            raise ValueError("limit must be an integer in [1, 10000]")
        pattern = self._pattern(image)
        if region is not None and pattern.region is not None and region != pattern.region:
            raise ValueError("Specify the search region either on Pattern or the method")
        search = region if region is not None else pattern.region
        template = self._template(pattern)
        screen = self.capture()
        self._region(search, screen)
        self._check()
        try:
            found = find_scaled(screen.to_numpy(), template, pattern.similarity, search,
                                scales=pattern.scales, max_results=limit, preprocess=pattern.preprocessing)
        except ValueError as error:
            raise errors.InvalidAsset(str(error)) from error
        self._check()
        output = [Match(item.region, item.score, self.serial, screen.resolution, screen.frame_id,
                        pattern.path, pattern.target_offset) for item in found]
        self._emit("recognition", template=pattern.path, count=len(output), frame_id=screen.frame_id,
                   matches=[{"x": item.region.x, "y": item.region.y, "width": item.region.width,
                             "height": item.region.height, "score": item.score} for item in output[:100]])
        return output

    def recognizeText(self, *, region: Region | None = None, language: str = "eng", confidence: float = 0,
                      timeout: float = 10, psm: int = 6, preprocess: str = "grayscale") -> OCRResult:
        """Fresh OCR with word boxes and confidence 0–100; local Tesseract/data required.

        Original coordinates; max 4MP search area. Native OCR is bounded to
        0<timeout<=60 seconds and checks pause/cancellation while the owned
        process runs. No files/models are downloaded. Missing engine/model
        raises OCRUnavailable, process/output failures OCRFailed.
        """
        from app.vision.ocr import TesseractOCR, OcrUnavailable, OcrFailure
        screen = self.capture()
        self._region(region, screen)
        if self._ocr is None:
            self._ocr = TesseractOCR()
        try:
            result = self._ocr.recognize(screen.to_numpy(), region=region, language=language, confidence=confidence,
                                         timeout=timeout, psm=psm, preprocess=preprocess, checkpoint=self._check)
        except OcrUnavailable as error:
            raise errors.OCRUnavailable(str(error)) from error
        except OcrFailure as error:
            raise errors.OCRFailed(str(error)) from error
        except TimeoutError as error:
            raise errors.RecognitionTimeout(str(error)) from error
        self._check()
        words = tuple(TextMatch(w.text,w.confidence,w.region,self.serial,screen.resolution,screen.frame_id,w.line) for w in result.words)
        self._emit("recognition", method="ocr", count=len(words), frame_id=screen.frame_id)
        return OCRResult(result.text, words)

    def readText(self, *, region: Region | None = None, language: str = "eng", confidence: float = 0,
                 timeout: float = 10, psm: int = 6, preprocess: str = "grayscale") -> str:
        """Return recognized text, or empty string for real text absence; failures propagate."""
        return self.recognizeText(region=region,language=language,confidence=confidence,timeout=timeout,psm=psm,preprocess=preprocess).text

    def findText(self, text: str, *, region: Region | None = None, exact: bool = True, case_sensitive: bool = False,
                 confidence: float = 50, language: str = "eng", timeout: float = 10) -> list[TextMatch]:
        """Fresh OCR phrase search; exact whole words or tolerant substring, same line.

        Returns device-bound boxes, row/read order; no match gives []. Matching
        normalizes whitespace and optionally case. Substring boxes cover whole
        recognized words, not guessed character positions. Errors propagate.
        """
        from app.vision.ocr import TextResult, TextBox, search_text
        if not isinstance(text,str) or not text.strip() or len(text)>500 or type(exact) is not bool or type(case_sensitive) is not bool:
            raise ValueError("Use a nonempty text query and boolean exact/case_sensitive options")
        result = self.recognizeText(region=region, language=language, confidence=confidence, timeout=timeout)
        words = tuple(TextBox(w.text,w.confidence,w.region,w.line) for w in result.words)
        found = search_text(TextResult(result.text,words),text,exact=exact,case_sensitive=case_sensitive)
        if not result.words:
            return []
        sample=result.words[0]
        return [TextMatch(w.text,w.confidence,w.region,self.serial,sample.source_size,sample.frame_id,w.line) for w in found]

    def textExists(self, text: str, *, region: Region | None = None, exact: bool = True, case_sensitive: bool = False,
                   confidence: float = 50, language: str = "eng", timeout: float = 10) -> bool:
        """True if at least one OCR phrase matches; missing engines and errors are not False."""
        return bool(self.findText(text,region=region,exact=exact,case_sensitive=case_sensitive,confidence=confidence,language=language,timeout=timeout))

    def waitText(self, text: str, timeout: float = 10, *, region: Region | None = None, exact: bool = True,
                 case_sensitive: bool = False, confidence: float = 50, language: str = "eng", poll_interval: float = .2) -> TextMatch:
        """Wait for one unique OCR phrase; wall-clock timeout includes captures/OCR/pauses.

        timeout=0 makes one bounded attempt. Multiple matches raise AmbiguousMatch;
        missing engine/models and device failures propagate without blind retries.
        """
        timeout=seconds(timeout,"timeout")
        interval=seconds(poll_interval,"poll_interval",positive=True,maximum=60)
        deadline=time.monotonic()+timeout
        while True:
            self._check()
            remaining=deadline-time.monotonic()
            if timeout>0 and remaining<=0:
                raise errors.RecognitionTimeout(f"Text did not appear within {timeout:g}s: {text}")
            matches=self.findText(text,region=region,exact=exact,case_sensitive=case_sensitive,confidence=confidence,
                                  language=language,timeout=min(10,remaining) if timeout>0 else 10)
            if timeout>0 and time.monotonic()>deadline:
                raise errors.RecognitionTimeout(f"Text recognition exceeded {timeout:g}s")
            if len(matches)>1:
                raise errors.AmbiguousMatch(f"Multiple text targets matched: {text}")
            if matches:
                return matches[0]
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise errors.RecognitionTimeout(f"Text did not appear within {timeout:g}s: {text}")
            self.sleep(min(interval,remaining))

    def find(self, image: str | Pattern, *, region: Region | None = None) -> Match:
        """One capture/search; raise ImageNotFound or AmbiguousMatch instead of guessing."""
        matches = self.findAll(image, region=region, limit=2)
        if not matches:
            raise errors.ImageNotFound(f"Image not found: {self._pattern(image).path}")
        if len(matches) > 1:
            raise errors.AmbiguousMatch(f"Multiple image targets matched: {self._pattern(image).path}; use findAll or a smaller Region")
        return matches[0]

    def exists(self, image: str | Pattern, *, region: Region | None = None) -> Match | None:
        """Return one Match or None; never swallow missing assets/transport/ambiguity errors."""
        try:
            return self.find(image, region=region)
        except errors.ImageNotFound:
            return None

    def waitImage(self, image: str | Pattern, timeout: float = 10.0, *, poll_interval: float = 0.2) -> Match:
        """Poll for one unambiguous image; timeout is wall seconds, including pauses.

        Zero timeout makes one capture/search attempt. For positive timeouts,
        capture/recognition must finish within the deadline. An already running
        capture cannot be interrupted here and is still bounded by its backend.
        Missing/invalid assets, ambiguity and device errors propagate immediately.
        """
        timeout = seconds(timeout, "timeout")
        interval = seconds(poll_interval, "poll_interval", positive=True, maximum=60)
        deadline = time.monotonic() + timeout
        attempted = False

        def expired():
            return (attempted or timeout > 0) and time.monotonic() >= deadline

        def failure():
            return errors.RecognitionTimeout(f"Image did not appear within {timeout:g}s: {self._pattern(image).path}")

        while True:
            self._check()
            if expired():
                raise failure()
            try:
                match = self.find(image)
                if timeout > 0 and time.monotonic() > deadline:
                    raise failure()
                return match
            except errors.ImageNotFound:
                attempted = True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise failure() from None
                self.sleep(min(interval, remaining))

    def waitVanish(self, image: str | Pattern, timeout: float = 15.0, *, poll_interval: float = 0.2) -> None:
        """Wait until a valid capture contains no matches; capture failure is not success.

        A zero timeout allows one immediate attempt. Positive deadlines include
        capture time and pauses, with transport interruption bounded separately.
        """
        timeout = seconds(timeout, "timeout")
        interval = seconds(poll_interval, "poll_interval", positive=True, maximum=60)
        deadline = time.monotonic() + timeout
        attempted = False
        while True:
            self._check()
            if (attempted or timeout > 0) and time.monotonic() >= deadline:
                raise errors.RecognitionTimeout(f"Image did not vanish within {timeout:g}s: {self._pattern(image).path}")
            matches = self.findAll(image, limit=1)
            attempted = True
            if timeout > 0 and time.monotonic() > deadline:
                raise errors.RecognitionTimeout(f"Image did not vanish within {timeout:g}s: {self._pattern(image).path}")
            if not matches:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise errors.RecognitionTimeout(f"Image did not vanish within {timeout:g}s: {self._pattern(image).path}")
            self.sleep(min(interval, remaining))

    def sleep(self, seconds: float) -> None:
        """Cancellable/pause-aware delay of finite 0–86400 seconds."""
        duration = globals()["seconds"](seconds, "seconds")
        self._check()
        if self._interruptible_wait is not None:
            self._interruptible_wait(duration)
        else:
            deadline = time.monotonic() + duration
            while True:
                self._check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))
        self._check()

    def wait(self, target: float | str | Pattern, timeout: float | None = None) -> Match | None:
        """wait(number) delays; wait(image, timeout=10) delegates to waitImage."""
        if isinstance(target, (int, float)) and not isinstance(target, bool):
            if timeout is not None:
                raise TypeError("wait(number) does not accept an image timeout")
            self.sleep(target)
            return None
        if isinstance(target, (str, Pattern)):
            return self.waitImage(target, timeout=10.0 if timeout is None else timeout)
        raise TypeError("wait expects a numeric delay, image reference or Pattern")

    def back(self) -> None:
        """Send Android BACK to this assigned phone."""
        self._action("key", lambda: self._backend.key("KEYCODE_BACK"), key="KEYCODE_BACK")

    def home(self) -> None:
        """Send Android HOME to this assigned phone."""
        self._action("key", lambda: self._backend.key("KEYCODE_HOME"), key="KEYCODE_HOME")

    def launchApp(self, package: str) -> None:
        """Launch a validated installed Android package; backend failures propagate."""
        self._action("launch_app", lambda: self._backend.launch_app(package), package=package)

    def stopApp(self, package: str) -> None:
        """Force-stop a validated Android package on this assigned phone."""
        self._action("stop_app", lambda: self._backend.stop_app(package), package=package)

    def typeText(self, text: str) -> None:
        """Type supported text (up to 4096 characters); log only its character count.

        Unsupported Unicode is an explicit backend capability error. Text is
        never included in the built-in action event because it may be sensitive.
        """
        if not isinstance(text, str) or len(text) > 4096:
            raise ValueError("Text must be a string of at most 4096 characters")
        self._action("type_text", lambda: self._backend.type_text(text), characters=len(text))
