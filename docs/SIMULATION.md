# Offline simulation

Launch the normal app, then **Start Demo Session** on the welcome page, **Devices → Start Demo Session** (`Ctrl+Shift+D`), or **Device Manager → Simulation**. No phone, ADB installation, scrcpy server, OCR model or network service is required for a demo. Monaco/Python/Qt dependencies must already be installed.

Every demo is labeled **SIMULATED DEVICE — NOT CONNECTED TO ANDROID HARDWARE**. A failed real-device connection never starts or selects one. Demo input never passes through the ADB adapter or actual device registry.

## Three scenarios

| Scenario | Meaningful state transitions | Example |
| --- | --- | --- |
| Basic image click | Start → dashboard → complete | `click("start.png")`; then `click("continue.png")` |
| Wait and recognition | Loading → reward after a configured monotonic delay → complete after claim | `home()` restarts the timer; `click(waitImage("reward.png", timeout=15))` |
| Recorded workflow | Start → menu; swipe up selects Task B; open → details → complete | Capture/record the preview, generate normal Python and replay |

Choose a scenario and delay (0–60 seconds) in the Simulation tab. **Start Demo Session** creates a new independent session and project. **Reset Demo** changes the selected simulator to those options, cancels old execution and invalidates its connection generation. **Open scenario script** opens the corresponding example without overwriting another buffer. A configured delay above the example's 15-second wait intentionally causes a timeout; edit it explicitly when appropriate.

On compact screens, the Preview header button switches dense tool pages between full-width tools and phone preview; Back to tools returns to the recorder/forms. The Simulation tab scrolls to keep every setting reachable.

The header selector chooses between demos and real phones. Up to four demos can be active. Start them explicitly; each has its own state and worker lease. Run the example on one, then select another and run a different script. Multi-select real phones remains supported; simultaneous demo runs are started one at a time through the selector. Logs and execution rows include independent identities.

## Workflows

1. Start Basic image click. The current project contains real cropped `images/start.png` and ordinary scripts in `scripts/`.
2. In **Visual Tools**, capture a region, crop the Start button, save it under `images/`, insert a reference and test a fresh frame with OpenCV. This performs the same recognition used by the real API on generated pixels.
3. In Script Studio, run `click("start.png")`. Review and approve the source snapshot. A spawned Python worker recognizes the button and changes the simulator database; the regular preview shows the new state.
4. Reset. In **Recorder**, start recording, click Start in the preview, and stop. Select the tap and **Convert to Image Target…**, crop/save, then generate Python or replay. See [Recorder](RECORDER.md).
5. Try `waitImage`, a deliberately missing target, Pause/Resume, Stop and the global emergency stop. Reset emergency stop explicitly before another run.
6. **Pause** in the preview pauses rendering only. Script pause is the toolbar/F6 control. **Stop Demo** cancels its script and disconnects that simulator; saved project files remain.

Projects are created in the user's application-data `AndroidAutomationStudio/demo-projects` directory; `STUDIO_DATA_DIR` can choose a writable root. Each fresh project has a unique name and existing project/script buffers are preserved. Demo projects remain after exit; use your file manager to remove only projects you no longer want. State databases live in a private temporary directory and are closed/removed after workers and GUI jobs stop. Reset does not rewrite saved scripts/images. Saved recorder evidence can contain full screenshots; review it before sharing.

## Transport and limits

The simulation backend shares short SQLite transactions between the GUI pool and spawned workers. Each `sim://` identity requires an explicit database/token/generation capability. Reset/stop revoke old clients. Strict simulation IDs are rejected as ADB serials and cannot enter the real registry. No server or remote debug port is opened. These guards prevent accidental built-in command crossover; trusted Python is not a hostile-code sandbox and retains host-user permissions.

Screens are fixed 360 × 720 RGB, rendered locally at a modest 150 ms GUI update interval with one capture in flight per session. This is state visualization, **not Android or scrcpy video**. Taps, directional swipes, Home/Back, screenshot/recognition and conservative ASCII input are supported. Swipe duration is validated but does not model Android gesture timing; long press/double tap are input sequences without full Android gesture semantics. No installed APKs, Android services, physical keyboard/IME, sensor, real rotation, GPU, USB, Wi-Fi ADB or encoder behavior is simulated. `launchApp` / `stopApp` raise `UnsupportedCapability`. Passing these tests is not proof of Android compatibility.

For the retained terminal-only known-image fixture: `.venv/bin/python -m examples.run_visual_fixture`. It is separate from the integrated GUI demo.
