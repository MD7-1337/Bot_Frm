# Foundational Python scripting API

Latest alpha UI/diagnostic and recorder changes are reported in
[ALPHA_STABILIZATION.md](ALPHA_STABILIZATION.md). RGB pixel/color commands below
are part of the real serial-bound scripting API; OCR is still not implemented.

Implemented contract, 2026-10-30. This reference describes the executable API,
not the broader proposed API in the original blueprint. All commands below are
available as short functions and as methods on the worker-injected `device`.
They use the same implementation and the same assigned serial.

```python
target = Pattern("start.png").similar(0.9).targetOffset(4, -2)
if exists(target):
    point = click(target)
wait(2)
match = device.waitImage("reward.png", timeout=10)
device.click(match)
```

Imports also work inside a worker:

```python
from app.automation.api import click, Pattern, AssetNotFound
try:
    click(Pattern("start.png").similar(0.95))
except AssetNotFound as error:
    print(error)
```

Imported short functions use a `ContextVar`, not a global current phone. Calling
them outside an assigned context raises `NoExecutionContext`. A new thread does
not inherit another thread's assigned short-function context. `device` is the
explicit bound object for this run; there is no implicit cross-phone lookup.
The old `getDevice()` return contract remains the serial string.

## Targets and return values

| Type | Implemented contract |
| --- | --- |
| `Location(x: int, y: int)` | Nonnegative Android pixel coordinates. Touch operations additionally validate against a fresh full-device capture. |
| `Region(x: int, y: int, width: int, height: int)` | Nonnegative origin, positive extent; recognition rejects any part outside the current full screenshot. |
| `Offset(x: int = 0, y: int = 0)` | Signed integer displacement from an image match center, limited to ±100000 px per axis. |
| `Pattern(path: str, similarity: float = 0.85, region: Region \| None = None, target_offset: Offset = Offset(), scales: tuple[float, ...] = (1.0,))` | Immutable image reference. `.similar(score)`, `.inRegion(region)`, `.targetOffset(dx, dy)` and `.atScales(*scales)` return new values. Scales contain 1–16 finite values in [0.1, 4]; default is exactly one original-size search. |
| `Match` | Immutable region, score, `device_serial`, `source_size`, `frame_id`, template and target offset. `.target` computes center plus offset and rejects an out-of-screen result. A match from another serial is rejected before input. Changed source dimensions require a new search. |
| `Screen` | Immutable full-resolution RGB bytes, serial, width/height, frame ID and host monotonic capture-arrival timestamp. `.resolution` is `(width, height)`; `.to_numpy()` returns a read-only RGB view. Use `.copy()` to edit pixels. |

`Target = str | Pattern | Match | Location | tuple[int, int]`.
Coordinates always refer to the original device screen, never scaled preview
pixels. A match is evidence from a past capture, not a guarantee that the app
will remain unchanged before input. Scores are normalized matching scores, not
probabilities. Constant/invalid templates fail explicitly.

For explicit template resizing, use `Pattern("start.png").atScales(0.75, 1, 1.25)`.
All recognition methods and image-based touch commands use those scales. Returned
rectangles reflect the resized template in original screen coordinates; offsets
remain original pixels. Cross-scale overlap suppression removes duplicates. No
scale is implicit when excluded, and duplicate dimensions are searched once.
Scales add native matching work; extremely small, spatially constant resizes are
skipped. This is correlation, not OCR or general resolution independence.

## Actions

| Signature | Result / behavior |
| --- | --- |
| `click(target: Target) -> Location` | Resolve a unique image or explicit coordinate, tap once, return the actual target point. No automatic retries. |
| `doubleClick(target: Target, interval: float = 0.1) -> Location` | Resolve once and send two taps, with cancellable requested delay 0–1 s. Revalidate source size before the second tap. Backend latency adds to the actual interval. |
| `longPress(target: Target, duration: float = 2.0) -> Location` | Stationary ADB swipe; 0 < duration ≤ 60 s. |
| `tap(x: int, y: int) -> None` | Fresh screen-bound coordinate check followed by one input command. Booleans/floats/out-of-bounds coordinates are invalid. |
| `swipe(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> None` | Validate both endpoints on a fresh capture, then Android press/move/release; 0 < duration ≤ 60 s. |
| `drag(x1: int, y1: int, x2: int, y2: int, duration: float = 1.0) -> None` | Supported ADB endpoint swipe. It is not a continuous raw-touch path. |
| `scroll(direction: str, amount: int = 3) -> None` | 1–100 directional swipes. Direction is **finger motion**, one of `up/down/left/right`; application content behavior varies. Too-small screens raise `UnsupportedCapability`. This does not assert that a particular game supports scrolling. |
| `back() -> None`, `home() -> None` | Send Android BACK/HOME to this serial. |
| `launchApp(package: str) -> None` | Validate package, resolve one supported MAIN/LAUNCHER activity, run `am start -W`, require `Status: ok`. This confirms Android accepted launch, not that the application's loading finished. |
| `stopApp(package: str) -> None` | Verify installed package with `pm path`, then force-stop; Android error output is not treated as success merely because exit code is zero. |
| `typeText(text: str) -> None` | Supported conservative ASCII subset: letters, digits, spaces and `,.@_:/+-`. Other text, Unicode and shell metacharacters raise `UnsupportedCapability` before input. Empty text is a no-op. Built-in action logs retain character count, not the entered plaintext. |

Package names are validated before remote-shell use. Normal transport operations
have a 10 s deadline; scripting gestures use at least `duration + 2 s` when
longer, restoring the original deadline afterwards. These checks do not make
input/application response atomic. Already-sent Android actions cannot be undone.

## Recognition, waits and screen access

| Signature | Result / behavior |
| --- | --- |
| `find(image: str \| Pattern, *, region: Region \| None = None) -> Match` | One capture/search. No result raises `ImageNotFound`; multiple distinct qualifying targets raise `AmbiguousMatch` instead of selecting one blindly. |
| `findAll(image: str \| Pattern, *, region: Region \| None = None, limit: int = 100) -> list[Match]` | One capture/search; score-descending results with overlap suppression. Limit is 1–10000. No matches gives `[]`. |
| `getPixel(x: int, y: int) -> tuple[int, int, int]` | One fresh original-resolution capture, return `(red, green, blue)` integer channels in [0,255]. Invalid screen coordinates raise `InvalidCoordinates`; capture/device failures propagate. No input is sent. |
| `findColor(color: tuple[int,int,int], tolerance: int = 0, *, region: Region \| None = None, limit: int = 100) -> list[Location]` | One capture, return pixel locations in row-major order, using inclusive per-channel absolute RGB difference ≤ tolerance. Channels/tolerance are integer [0,255], limit 1–10000. Region must lie wholly in the screen. No match returns `[]`; malformed color/tolerance/limit raises `ValueError`, invalid bounds raise `InvalidCoordinates`. Results are pixels, not clustered objects. |
| `exists(image: str \| Pattern, *, region: Region \| None = None) -> Match \| None` | Unique match or `None` for legitimate visual absence only. Missing files, invalid templates, ambiguity and connection failures still raise. |
| `waitImage(image: str \| Pattern, timeout: float = 10.0, *, poll_interval: float = 0.2) -> Match` | Poll for a unique match until a monotonic wall-clock deadline. |
| `waitVanish(image: str \| Pattern, timeout: float = 15.0, *, poll_interval: float = 0.2) -> None` | Poll until a valid capture contains zero matches. A capture/disconnection failure is never disappearance success. |
| `sleep(seconds: float) -> None` | Cancellation/pause-aware delay, finite 0–86400 s. |
| `wait(target: float \| str \| Pattern, timeout: float \| None = None) -> Match \| None` | Number means delay; image means `waitImage` with default 10 s. Numeric delay with an image timeout argument is rejected. `wait(2)` returns `None`; `wait("image.png")` returns `Match`. |
| `capture() -> Screen` | Fresh original-resolution screenshot; transport/decoding faults raise. Recognition uses this image, not stale or scaled preview video. |
| `getResolution() -> tuple[int, int]` | Width/height from a current full-device capture. |
| `getDevice() -> str` | Assigned ADB serial, retained for compatibility. `device.serial` returns the same identity. |

Similarity is finite in `[0, 1]` and inclusive. Supply a search region either on
Pattern or the method; conflicting regions are rejected. Templates larger than
the search area produce no matches. Target offsets are original-device pixels.

Image timeouts are finite 0–86400 s; polling interval is 0 < interval ≤ 60 s.
**Timeout zero permits one immediate capture/search.** With a positive timeout,
a result arriving after its deadline is rejected. Paused time and capture time
count toward the wall-clock deadline. An already-running native capture/match
cannot be preempted by the image-wait clock; its completion/transport deadline
can make the observed return later. Stop can force-terminate a stuck worker.

## Project image resolution

Choose the project directory through **File → Choose project image library…**.
Scripts opened under an explicitly selected project retain that context. Other
scripts auto-discover the nearest `project.json`; otherwise a conventional
`scripts/` parent or the script directory is used. Discovery does not execute or
parse project manifests.

```text
MyProject/
  project.json
  scripts/main.py
  scripts/helpers.py
  images/start.png
  images/reward.png
```

- `"start.png"` prefers `project/images`, then script directory/project root.
- `"images/start.png"` is explicitly project-relative.
- Script-relative `"../images/start.png"` is supported if it stays inside the project.
- Absolute image paths are accepted only inside the selected project.
- PNG/JPEG/BMP/WebP files are supported, at most 16 MiB per asset.
- Traversal, symlink escapes, URLs, unsupported extensions and malformed paths
  are rejected. Template decoded pixels are limited separately.

Capture defaults to `project/images`, atomically saves the cropped PNG and
inserts ordinary Python:

```python
image_path = "../images/start.png"
click(image_path)
```

If a user saves outside the active project, the file is preserved but an unusable
reference is not silently inserted. The editor resolves literal references with
the same library rules, adds missing-image warnings and shows bounded hover
thumbnails. Source text remains valid `.py`; decorations are not binary objects.

## Exceptions

All built-in engine failures derive from `AutomationError`:

| Exception | Meaning |
| --- | --- |
| `NoExecutionContext` | Imported short function used without a bound run. |
| `AssetNotFound` | Referenced project image is missing; also a `FileNotFoundError`. |
| `InvalidAsset` | Unsafe path, invalid/oversized image, degenerate template; also `ValueError`. |
| `InvalidCoordinates` | Coordinates, offset or region outside screen bounds; also `ValueError`. |
| `CrossDeviceTarget` | A Match/backend identity belongs to another serial. |
| `ImageNotFound` | A valid search found no qualifying image. |
| `AmbiguousMatch` | More than one target qualified for a unique-target operation. |
| `RecognitionTimeout` | Image appearance/disappearance wait exceeded its budget. |
| `FrameUnavailable` | Screenshot data is missing/invalid or cannot be decoded. |
| `DeviceDisconnected`, `DeviceOffline`, `DeviceUnauthorized` | Distinct observed device/transport availability failures. |
| `CommandTimeout` | Transport deadline expired; sent action outcome may be ambiguous. |
| `CommandFailed` | Android rejected/failed a command, including zero-exit error output or permissions. |
| `UnsupportedCapability` | This backend cannot represent the requested input/feature. |
| `Cancelled` | Cooperative execution stop; terminal state cancelled. |

Malformed argument types and invalid scalar settings additionally raise ordinary
`TypeError`/`ValueError`. User exceptions are ordinary Python exceptions and are
reported with run ID, serial, source path/line and a bounded traceback from the
exact source buffer executed.

## Run, pause, resume and stop

- F5 runs the current source snapshot on the current phone after trust approval.
- Ctrl+F5 runs it independently on selected phones; Ctrl/Shift selects device rows.
- **Execution → Assign Python file…** associates a file with the current phone;
  **Run assigned files…** runs different files on selected phones.
- Select a row in **Script runs**, then F6 pauses, Shift+F6 resumes and Shift+F5
  stops that run. Without a selected run row, controls use the current phone's
  active run. Pause is shown only after the worker acknowledges a safe point.
- Ctrl+Shift+F12 latches global emergency stop. Reset explicitly before new input.
- Output/errors retain device/script identity. Execution-line decoration updates
  from a coalesced 20 Hz worker mailbox, including blocking waits. Editing the
  buffer clears stale highlighting; this is not a breakpoint debugger.

Workers use Windows-compatible spawn. Normal Python conditions/loops, functions,
classes, imports, `__main__` guards and exception handling run inside the worker,
with project/script import paths and per-process globals. Pausing applies at
Python project-line/API checkpoints; native calls and third-party threads may
not pause until they return to one. Cancellation/forced termination is bounded.
Lost connection generations cancel only their own work; reconnecting does not
revive old starts or replay actions.

**Trust boundary:** arbitrary Python has host-user permissions. Process isolation,
path validation and the approval dialog are not an OS sandbox. Built-in device
leases do not restrict other programs or deliberate raw ADB access. User-created
descendant processes/threads are not fully contained. No script execution or
device control is exposed through the editor web bridge.

## Runnable examples

`examples/visual_script.py` and `examples/explicit_device_script.py` demonstrate
the two styles. They expect an assigned worker and project `images/start.png`.

For a complete phone-free run that generates known PNG fixtures and executes
both styles in separate actual worker processes:

```bash
.venv/bin/python -m examples.run_visual_fixture
```

That command explicitly uses mock devices, not physical Android hardware. Linux
tests do not establish Windows or real-device compatibility.
