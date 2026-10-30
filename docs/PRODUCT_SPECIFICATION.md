# ANDROID AUTOMATION STUDIO
## FINAL MASTER DEVELOPMENT PROMPT — VERSION 2.0

**Project type:** Professional Windows Desktop Application  
**Primary language:** Python  
**GUI framework:** PySide6 / Qt  
**Script editor:** Monaco Editor + Qt WebEngine + QWebChannel  
**Target platform:** Windows 10/11, 64-bit  
**Purpose:** Multi-device Android automation and visual scripting IDE

---

# 1. YOUR ROLE AND MISSION

You are an expert team consisting of:

- Senior software architect
- Expert Python developer
- PySide6 / Qt GUI engineer
- Android ADB and scrcpy integration specialist
- Computer vision / OpenCV engineer
- IDE and code-editor developer
- UI/UX product designer
- Software security engineer
- QA and automated testing engineer
- Windows deployment engineer

Your task is to **design, implement, test, document, and package a complete production-quality Windows desktop application named Android Automation Studio**.

Do not build a simple demonstration, fake GUI, single-file script, or unfinished prototype and present it as the final product.

Develop a real modular application that fulfills the requirements below.

The user has already made the main product and technology decisions. Respect those decisions instead of repeatedly asking which technologies or features to use.

Work in phases, make engineering decisions where necessary, document tradeoffs, and verify functionality.

# 2. PROJECT VISION

Android Automation Studio is a Windows application that combines the best concepts of:

1. **SikuliX** — Visual scripting through screenshots, image recognition, conditions, and automation commands.
2. **scrcpy** — Real-time Android screen mirroring and interaction.
3. **Python IDEs** — Powerful code editor, autocomplete, debugging, project management, and script execution.
4. **Multi-device automation systems** — Independent or shared script execution across multiple Android phones.
5. **Professional task schedulers** — Game switching, task queues, automation schedules, retries, monitoring, and recovery.

## Fundamental concept

The Windows PC is the **control center**.

The games and target applications run on actual Android devices, not on the Windows PC.

The program should let a user:

- Connect one or many Android phones.
- View and control their screens.
- Capture image targets from those screens.
- Write Python scripts using SikuliX-style commands.
- Generate scripts through visual tools and action recording.
- Execute one script on multiple phones or different scripts on each phone.
- Manage multiple games sequentially on each phone.
- Monitor, debug, schedule, and recover automation tasks.
- Save reusable projects, scripts, screenshots, and settings.

The application must be suitable for beginners while giving advanced users substantial scripting and debugging control.

## Important product boundaries

- Android phones are the automation targets.
- A phone normally runs one foreground game or application at a time.
- Multiple games on one phone are supported through automated switching and sequential execution.
- Simultaneous automation of multiple phones is required.
- Core functionality must work without internet access, although local USB or Wi-Fi communication may be needed.
- Root access should not be required for standard operations.
- Device and Android version limitations must be handled transparently.

# 3. CONFIRMED TECHNOLOGY STACK

Use this core architecture:

| Component | Technology |
|---|---|
| Main application | Python |
| Windows interface | PySide6 / Qt |
| UI styling | Qt Widgets, Qt Style Sheets, optional QML |
| Script editor | Monaco Editor |
| Embedded editor runtime | Qt WebEngine |
| Editor/backend communication | Qt WebChannel |
| Android communication | Android Debug Bridge (ADB) |
| Android screen mirroring | scrcpy-based integration |
| Computer vision | OpenCV |
| OCR | Suitable offline OCR engine, chosen after evaluation |
| Data storage | SQLite and project files |
| Python debugging | debugpy or equivalent |
| Background execution | Managed Python worker processes |
| Packaging | Suitable Windows Python packager |
| Distribution | Windows installer and portable release |

These are architecture requirements, except where an alternative must be evaluated for compatibility, reliability, licensing, or performance.

## Technology design rules

- Use a supported Python version and pin tested dependencies.
- Keep UI, automation, device management, and storage separated.
- Do not run blocking automation on the Qt GUI thread.
- Avoid introducing C++, Rust, Node.js, or other runtimes unnecessarily. Use native components when needed for efficient video decoding or system integration.
- Bundle Monaco's required resources locally so editing works offline.
- Use QWebChannel as a controlled interface between Monaco and Python.
- Do not expose unrestricted Python execution through the editor's web bridge.
- Ensure package versions and third-party licenses are compatible with distribution.

# 4. SOFTWARE ARCHITECTURE

Design the program using a modular, maintainable architecture.

## Required subsystems

1. Application Shell and UI System
2. Device Discovery and Connection Manager
3. ADB Communication Layer
4. scrcpy-Compatible Video and Control Layer
5. Embedded Phone Preview Manager
6. Python Script Editor
7. Visual Scripting and Image Capture Tools
8. Automation Runtime and Script API
9. Computer Vision and OCR Engine
10. Script Recording and Replay Engine
11. Debugging and Testing System
12. Multi-Device Execution Coordinator
13. Game and Task Scheduler
14. Recovery and Failure Management
15. Project and Asset Manager
16. Settings and Security Manager
17. Logging and Performance Monitoring
18. Installer, Updater, and Diagnostics System

## Architecture requirements

Each module must have a clearly defined responsibility and interface.

The GUI must communicate with automation services through structured events and commands.

Design suitable typed messages or data models for:

- Device connection and disconnection.
- Screen frames.
- Device control requests.
- Script execution requests.
- Script status.
- Recognition results.
- Debugger events.
- Error and recovery events.
- Task scheduling events.
- Performance statistics.

Use thread-safe and process-safe communication.

Each phone must have an independent identity, runtime state, and control context.

Prevent multiple uncoordinated workers from sending conflicting actions to the same phone.

The architecture must allow components to be tested without real phones by using mock device adapters.

# 5. COMPLETE GUI/UX DESIGN

Create a professional application inspired by modern programming IDEs and Windows Fluent Design.

The appearance should be:

- Clean and modern.
- Professional rather than gaming-themed.
- Comfortable for long programming sessions.
- Consistent across workspaces.
- Visually polished but not unnecessarily animated.
- Accessible and usable across different monitor sizes.

## Main navigation

Provide these primary workspaces:

### A. Script Studio

The main programming and automation-development workspace.

Contains:

- Project explorer.
- Python code editor.
- Image asset library.
- SikuliX-style automation toolbar.
- Embedded Android phone preview.
- Screenshot and coordinate tools.
- Record and replay controls.
- Execution toolbar.
- Debugger.
- Logs and console.

### B. Device Manager

For connecting and controlling Android phones.

Contains:

- Device list.
- Phone preview grid.
- Device grouping.
- USB/Wi-Fi connection controls.
- Device settings.
- Phone status and metrics.
- Individual and group actions.

### C. Task Manager

For organizing automation work.

Contains:

- Task queues.
- Script assignments.
- Scheduling.
- Priorities.
- Game switching workflows.
- Retry and recovery policies.
- Execution history.

### D. Monitoring

For observing running automation.

Contains:

- Running script overview.
- Per-phone statuses.
- Error information.
- Device metrics.
- CPU/RAM usage.
- Execution logs.
- Recovery history.
- Performance graphs.

Also include accessible Settings, Help, Diagnostics, and Project Management views.

## Workspace customization

Support:

- Dockable panels.
- Detachable panels.
- Resizable splitters.
- Multiple monitors.
- Drag-and-drop panel arrangement.
- Panel visibility controls.
- Saving and restoring layouts.
- Reset to default.
- Layout persistence after restarting the program.

## Workspace presets

Provide at least:

**Coding:** Large Python editor, project explorer, phone preview.

**Device Control:** Multi-phone preview grid with device controls.

**Debugging:** Code, breakpoints, variables, phone preview, logs.

**Task Planning:** Task queues, schedules, and assignments.

## Visual customization

Provide:

- Dark theme.
- Light theme.
- Follow Windows system theme.
- Adjustable editor fonts and sizes.
- Configurable keyboard shortcuts.
- Professional icons.
- Consistent spacing and typography.
- Optional compact density mode.
- High-DPI scaling support.

Use appropriate Qt docking/layout systems instead of building a fragile manual window arrangement.

## Usability requirements

- Clear navigation.
- Context menus.
- Useful tooltips.
- Command search.
- Keyboard navigation.
- Descriptive error messages.
- Non-intrusive notifications.
- First-run onboarding.
- Beginner tutorials.
- Built-in scripting documentation.
- Accessible focus indicators and controls.

Avoid clutter, excessive animation, and unnecessarily complex workflows.

# 6. ADVANCED ANDROID DEVICE MANAGER

The application must detect, connect, and manage multiple Android phones.

## Connection methods

Support:

- USB ADB.
- Wi-Fi ADB.
- Android wireless debugging pairing where supported.
- Manual device connection.
- Automatic device detection.
- Connection status updates.
- Automatic reconnection with safe recovery policies.

## Device identification

Each device must be identified using its actual ADB serial or another verified unique connection identifier.

Allow users to assign custom names and groups.

Show available information:

- Device name.
- Manufacturer and model.
- Android version.
- Device serial.
- Connection type.
- Connection status.
- Battery percentage.
- Charging status.
- Screen resolution.
- Screen orientation.
- Assigned scripts.
- Current task.
- Automation state.

Handle unsupported device information without crashing or displaying invented values.

## Device management actions

Provide:

- Connect.
- Disconnect.
- Reconnect.
- Rename.
- Assign group.
- Open preview.
- Start assigned script.
- Pause script.
- Resume script.
- Stop script.
- Launch application.
- Stop application.
- Android Home.
- Android Back.
- Screenshot.

Allow operations on one selected phone or a selected group.

## Isolation requirement

Every ADB operation must target the intended device.

Never depend on whichever device ADB considers the default when multiple phones are connected.

Handle device disconnection, unauthorized ADB states, offline devices, and permission problems explicitly.

# 7. EMBEDDED SCRCPY-STYLE PHONE PREVIEWS

This is a core feature.

Phone screens must appear **inside the Windows application**, not only as separate scrcpy windows.

Support both embedded and detachable previews.

## Preview capabilities

- Live Android screen.
- Individual device preview.
- Multiple-phone grid.
- Fullscreen or enlarged preview.
- Detach into independent windows.
- Reattach to main workspace.
- Multiple-monitor support.
- Zoom in/out.
- Fit-to-window.
- Orientation changes.
- Configurable FPS.
- Configurable streaming quality.

## Interactive control

Users must be able to:

- Click or tap the preview.
- Double tap.
- Long press.
- Swipe.
- Drag.
- Scroll where supported.
- Send keyboard actions.
- Open Android navigation controls.
- Capture screenshots.
- Pick screen coordinates.

Map all user interactions to the correct Android coordinates, accounting for scaling, letterboxing, zoom, rotation, and viewport offsets.

## Visual overlays

Support overlays for:

- Selected screenshot regions.
- Detected image matches.
- Match confidence.
- Target coordinates.
- Tap points.
- Swipe paths.
- Debugging indicators.

Overlays must not modify the actual screenshot pixels used for recognition.

## Important video implementation constraint

scrcpy's internal server/client protocol is version-sensitive.

Do not assume the standard scrcpy GUI can simply become a stable embedded Qt widget.

Begin with a technical proof of concept to establish a reliable embedded streaming strategy.

Possible solutions include a compatible pinned-version client, appropriate video decoding libraries, and native Qt-compatible frame rendering.

Keep video transport separate from the visual preview widget.

Prefer one managed capture stream per device when possible, with frames shared efficiently between UI rendering and recognition.

Provide fallback external scrcpy windows or ADB screenshot capture when embedded streaming is unavailable.

Do not claim that embedded streaming is complete until it actually works and has been tested.

# 8. MONACO PYTHON SCRIPT EDITOR

Embed Monaco Editor using Qt WebEngine and connect it to Python using QWebChannel.

The editor should resemble a professional IDE.

## Required editor capabilities

- Python syntax highlighting.
- Line numbers.
- Automatic indentation.
- Autocomplete.
- Built-in automation API suggestions.
- Error highlighting.
- Signature help.
- Hover documentation.
- Search and replace.
- Multiple script tabs.
- Undo and redo.
- Code folding.
- Bracket matching.
- Keyboard shortcuts.
- Save and Save As.
- Script templates.
- Current execution line highlighting.
- Breakpoint indicators.
- Source diagnostics.

Implement the necessary Python language-service integration instead of assuming Monaco automatically provides full Python intelligence.

## SikuliX-style toolbar

Provide direct insertion tools for:

- Screenshot capture.
- Region selection.
- Coordinate selection.
- Click.
- Double click.
- Long press.
- Swipe.
- Drag.
- Scroll.
- Find image.
- Check image existence.
- Wait for image.
- Wait for image to vanish.
- OCR recognition.
- Pixel/color detection.
- Conditions.
- Loops.
- Delays.
- Android application controls.

When a user chooses a visual tool, generate valid Python code at the editor cursor position.

## Hybrid image representation

Keep Python scripts as ordinary valid `.py` files.

Example:

```python
click("start.png")
wait("reward.png", timeout=10)
```

Display useful visual image thumbnails beside the corresponding references using Monaco decorations, widgets, or equivalent supported extensions.

Support:

- Hover image previews.
- Click to open image editor.
- Image reference navigation.
- Missing-image warnings.
- Thumbnail caching.
- Correct updates when files change.

Do not replace Python string literals with non-Python binary image objects.

The saved source must remain readable and runnable independently of Monaco's visual decorations.

# 9. INTEGRATED SCREENSHOT AND IMAGE EDITOR

Build a visual screenshot tool inspired by SikuliX.

## Capture workflow

1. Select an Android phone.
2. Click Capture Image.
3. Obtain a screenshot.
4. Display the screenshot.
5. Allow drag-to-select a region.
6. Preview the selected image.
7. Name and save it.
8. Add it to the project's image library.
9. Automatically insert its reference into the Python editor.

## Screenshot features

- Full-screen capture.
- Rectangle selection.
- Crop.
- Zoom.
- Coordinate picker.
- Image target point.
- Click offsets.
- Save and rename.
- Preview and compare.
- Image metadata.
- Image organization.
- Target testing.
- Similarity configuration.
- Search-region configuration.

Support multiple image templates for different resolutions or layouts.

## Image testing

Provide a **Test Match** action that:

1. Captures a current device frame.
2. Searches for the reference image.
3. Displays any matches.
4. Shows similarity scores.
5. Highlights matched regions.
6. Shows computed tap locations.
7. Allows the user to adjust matching settings.
8. Reports failure or ambiguity clearly.

Similarity scores must be described accurately as matching scores, not guaranteed probabilities of correctness.

# 10. HYBRID COMPUTER VISION ENGINE

Implement a complete recognition system combining multiple methods.

## A. Image template matching

Using OpenCV, support:

- Template matching.
- Similarity thresholds.
- Multiple results.
- Search regions.
- Target offsets.
- Multi-scale matching.
- Multiple reference templates.
- Optional preprocessing.
- Duplicate or overlapping result filtering.
- Match result visualization.

## B. OCR

Support offline text recognition where practical.

Features:

- Read visible text.
- Search for text.
- Get detected text location.
- Find text within a region.
- Click detected text.
- Report confidence when available.
- Handle different languages when supported by the chosen OCR engine.

## C. Pixel/color recognition

Support:

- Read pixel color.
- Search for specific colors.
- Compare colors with tolerance.
- Detect color changes.
- Analyze selected regions.
- Evaluate color percentages.

## D. Android UI-element recognition

Where available, support Android UI hierarchy inspection or accessibility-based element discovery through supported interfaces.

Examples:

- Element text.
- Resource ID.
- Clickable elements.
- UI bounds.
- Element properties.

This is optional for apps where it is unsupported. Many games render custom graphics and will require computer vision.

## E. Fallback strategies

Allow recognition policies such as:

1. Try image matching.
2. Try a second template.
3. Try OCR.
4. Run a custom recovery action.
5. Stop or retry according to configuration.

Recognition methods must be modular and independently testable.

# 11. COMPLETE PYTHON AUTOMATION API

Create a documented Python library that users can call from their scripts.

The program must support **two scripting styles**.

## Style A — Simple SikuliX-style API

Commands automatically target the Android device assigned to the current script execution.

Example:

```python
while True:
    if exists("start.png"):
        click("start.png")

    wait(2)
```

## Style B — Explicit device API

Users can intentionally target a particular phone.

Example:

```python
phone = devices.get("phone_1")

phone.click("start.png")
phone.swipe(200, 700, 200, 300)
```

Both styles must use the same underlying automation implementation.

## Required API categories

### Touch

```python
click(target)
doubleClick(target)
longPress(target, duration=2)
tap(x, y)
swipe(x1, y1, x2, y2, duration=0.5)
drag(x1, y1, x2, y2, duration=1)
scroll(direction, amount=3)
```

### Recognition

```python
find("button.png")
findAll("button.png")
exists("button.png")
wait("button.png", timeout=10)
waitVanish("loading.png", timeout=15)
```

### Screen

```python
capture()
getPixel(100, 200)
getRegion(x, y, width, height)
getResolution()
```

### OCR

```python
readText()
textExists("START")
clickText("CLAIM REWARD")
```

### Android

```python
back()
home()
launchApp("com.example.app")
stopApp("com.example.app")
switchApp("com.example.other")
typeText("hello")
pressKey("ENTER")
```

### Device

```python
getDevice()
getBattery()
isConnected()
```

### Timing

```python
sleep(2)
wait(2)
```

Define `wait(2)` as a delay and `wait("image.png", timeout=10)` as an image wait if implementing SikuliX-compatible overloading.

Also provide explicit methods such as `sleep()` and `waitImage()` to avoid ambiguity.

### Object types

Create useful objects such as:

- `Location`
- `Region`
- `Pattern`
- `Match`
- `Device`
- `Screen`
- `RecognitionResult`

Support properties and methods such as:

```python
pattern = Pattern("start.png").similar(0.9)

if exists(pattern):
    click(pattern)
```

These examples define the desired API behavior. Implement and document exact signatures; they are not claims about existing library functions.

## API quality requirements

Every public function must have:

- Defined parameters.
- Defined return types.
- Useful exceptions.
- Timeout behavior.
- Cancellation support where applicable.
- Autocomplete information.
- Documentation.
- Working examples.
- Automated tests.

Support standard Python syntax, including conditions, loops, functions, modules, classes, and exception handling.

## Execution context safety

The simple API must always target the assigned phone.

Do not implement it using unsafe shared global device state.

Explicit cross-device access must be intentional and visible.

Prevent one user's script execution from accidentally changing another phone's device context.

# 12. ADVANCED SCRIPT RECORDING

Implement a record-and-replay system.

Users must be able to control their phones through the application and record those actions.

## Recording features

- Start recording.
- Stop recording.
- Pause recording.
- Record tap positions.
- Record double taps.
- Record long presses.
- Record swipe paths.
- Record drag actions.
- Record delays.
- Capture screenshots.
- Create image targets during recording.
- Generate editable Python code.
- Replay generated scripts.
- Test individual steps.

## Visual recording editor

Provide an action timeline.

Allow:

- Reorder actions.
- Delete actions.
- Edit coordinates.
- Edit delays.
- Convert coordinate actions into image-based actions.
- Add conditions.
- Insert loops.
- Save as Python script.

Example:

```python
click("start.png")
wait(2)
swipe(300, 700, 300, 200)
click("reward.png")
```

Recording must reliably capture actions made through our controlled preview.

Do not claim the recorder captures every physical touch occurring on the phone outside the application unless that capability has been specifically implemented and verified.

Generated scripts should remain editable ordinary Python files.

# 13. MULTI-PHONE AUTOMATION ENGINE

Support simultaneous automation across many devices.

## Mode 1 — Shared script

One Python script is assigned to multiple phones.

Example:

```text
farm.py
   |
   +-- Phone 1
   +-- Phone 2
   +-- Phone 3
```

Each phone has its own script execution instance, state, screenshots, and logs.

One phone may be on step 3 while another is on step 10.

A failure on one phone must not automatically stop the others.

## Mode 2 — Independent scripts

```text
Phone 1 -> farm.py
Phone 2 -> rewards.py
Phone 3 -> daily_tasks.py
```

The program executes these tasks independently.

## Execution features

- Start.
- Pause.
- Resume.
- Stop.
- Restart.
- Emergency stop.
- Device selection.
- Group execution.
- Independent status.
- Execution history.
- Per-phone logs.

## Concurrency

Use managed worker processes and efficient communication.

Workers must not block the GUI.

Provide bounded queues, cancellation signals, timeouts, and resource cleanup.

Avoid starting unlimited processes or threads as the device count grows.

Use per-device command serialization or an equivalent coordination mechanism.

# 14. PROFESSIONAL PYTHON DEBUGGING

Implement an integrated debugger appropriate for a professional IDE.

Use debugpy or another suitable Python debugger.

## Required features

- Set breakpoints.
- Remove breakpoints.
- Conditional breakpoints where supported.
- Step into.
- Step over.
- Step out.
- Continue.
- Pause.
- Stop.
- Display active source line.
- Inspect variables.
- Inspect call stack.
- View exceptions.
- Debug individual phones.
- Debug one script without blocking other scripts.

## Visual automation debugging

Allow users to:

- Test `click()` individually.
- Test `exists()` and `find()`.
- See image match locations.
- See similarity results.
- View the current phone screenshot.
- Inspect target coordinates.
- Capture screenshots on failure.
- View command duration.
- Diagnose timeouts.

## Emergency stop

Provide an always-accessible global emergency stop shortcut and button.

It must:

- Stop dispatching new automation commands.
- Cancel or terminate affected workers.
- Clean up device control sessions.
- Release held inputs where supported.
- Update execution states.

Document limitations when an already-sent Android command cannot be reversed.

# 15. ADVANCED GAME AND TASK MANAGER

Allow users to automate multiple Android games or apps on a single phone sequentially.

## Example workflow

```text
Phone 1
  |
  +-- Open Game A
  |     Run farm.py
  |     Complete
  |
  +-- Open Game B
  |     Run rewards.py
  |     Complete
  |
  +-- Open Game C
  |     Run daily.py
  |     Complete
  |
  +-- Repeat based on schedule
```

## Task system

Provide:

- Task creation.
- Task editing.
- Task deletion.
- Script assignment.
- Phone assignment.
- Device group assignment.
- Task queues.
- Task priorities.
- Task dependencies.
- Scheduled execution.
- Interval repetition.
- Maximum duration.
- Maximum retries.
- Task enable/disable.
- Execution history.

## Scheduler requirements

Persist schedules and state.

Prevent conflicting simultaneous tasks from controlling the same phone.

Support clear task states:

- Pending.
- Running.
- Paused.
- Completed.
- Failed.
- Cancelled.
- Recovering.

Provide a visual queue editor with drag-and-drop ordering and detailed task settings.

Validate schedules and handle missed runs or application restarts according to user-configured policies.

# 16. ADVANCED ERROR HANDLING AND RECOVERY

Implement a configurable recovery system.

## Errors to handle

- Image not found.
- Recognition timeout.
- Ambiguous matches.
- Device disconnected.
- ADB unauthorized.
- Android app closed.
- Game frozen or unresponsive.
- Script exception.
- Invalid image reference.
- Worker crash.
- Unsupported device command.

## Recovery actions

Support:

- Retry.
- Delay and retry.
- Skip action.
- Run recovery function.
- Restart application.
- Reconnect device.
- Restart script.
- Resume from safe checkpoint.
- Stop affected task.
- Notify user.

## Per-action recovery settings

Allow configuration of:

- Timeout.
- Retry count.
- Retry delay.
- Backoff policy.
- Failure behavior.
- Recovery function.

## Failure logging

Record:

- Error type.
- Timestamp.
- Device.
- Script.
- Source line.
- Screenshot if available.
- Recovery attempts.
- Final result.

Never blindly resume after a disconnect if doing so could duplicate an unsafe action.

Use explicit checkpoints and verified device state when possible.

# 17. PROFESSIONAL PROJECT MANAGEMENT

Users must be able to create and manage multiple automation projects.

## Example project layout

```text
MyAutomationProject/
├── project.json
├── scripts/
│   ├── farm.py
│   ├── rewards.py
│   └── common/
│       └── helpers.py
├── images/
│   ├── start.png
│   ├── reward.png
│   └── device_variants/
├── templates/
├── workflows/
├── settings/
└── logs/
```

The precise format can be refined, but it must be portable and documented.

## Project functions

- New project.
- Open project.
- Save project.
- Autosave.
- Recent projects.
- Project explorer.
- Rename files.
- Delete files.
- Import/export.
- Project search.
- Image asset manager.
- Reusable modules.
- Script templates.

## Advanced project features

- Local backups.
- Restore.
- Version history.
- Optional Git integration.
- Portable project packaging.
- Project migration across app versions.
- Safe handling of missing image references.
- Detection of unsaved changes.
- Atomic saves where practical.

Use SQLite for appropriate application metadata and scheduling data, but keep ordinary Python scripts and image assets in portable files.

Do not place sensitive credentials in exported projects or backups by default.

# 18. PERFORMANCE AND SCALABILITY

Build an architecture that works efficiently with a few phones and can expand toward **20 or more Android devices when hardware permits**.

Do not promise a fixed device count or FPS without benchmarks.

## Required optimization features

- Configurable preview FPS.
- Per-phone video quality.
- Adjustable frame resolution.
- Reduced FPS for background previews.
- Priority for the selected phone.
- Shared capture frames where practical.
- Efficient OpenCV operations.
- Region-specific recognition.
- Bounded frame queues.
- Avoid unnecessary screenshot copies.
- Managed worker counts.
- Resource-aware scheduling.

## Monitoring metrics

Display measurable values such as:

- Application CPU usage.
- Application RAM usage.
- Per-worker resource usage where available.
- Frame rate.
- Frame processing latency.
- Image recognition duration.
- Active task count.
- Device connectivity.
- Error rates.

## Performance profiles

Provide profiles such as:

- Low resource usage.
- Balanced.
- High responsiveness.
- Custom.

Allow per-phone overrides.

Benchmark realistic combinations of device counts, streaming FPS, and recognition workloads.

Keep the GUI responsive even when recognition or automation is busy.

# 19. SECURITY AND PRIVACY

The program runs Python scripts and controls Android devices, so security is essential.

## Script security

- Warn when importing untrusted scripts.
- Show script origin and trust status where available.
- Require clear user approval before execution.
- Support permission declarations for built-in automation services.
- Validate device control requests.
- Protect stored credentials.
- Prevent accidental targeting of unauthorized devices.
- Offer process isolation where technically practical.

**Important:** Ordinary Python code can access the host OS with the running user's permissions. A permission dialog by itself is not a complete Python sandbox.

Do not claim arbitrary untrusted Python is safely restricted unless actual OS-level isolation or equivalent protection is implemented and tested.

## Privacy

- Core operation works offline.
- No mandatory cloud account.
- No automatic upload of screenshots.
- Configurable log retention.
- Configurable screenshot retention.
- Explicit control over diagnostic exports.
- Clear privacy settings.
- Avoid collecting unrelated user information.
- Keep sensitive settings out of exported projects.

## Application security

- Validate IPC messages.
- Restrict Qt WebChannel interfaces to required methods.
- Prevent command injection in ADB or process invocations.
- Secure local file handling.
- Validate downloaded updates.
- Document third-party dependencies and licenses.
- Handle failures without leaking sensitive data.

# 20. APPLICATION SETTINGS

Provide a professional settings system.

## Categories

### General

Theme, language readiness, startup behavior, project location.

### Devices

ADB configuration, Wi-Fi settings, device naming, reconnection policies.

### Video

Resolution, FPS, bitrate/quality, preview behavior.

### Automation

Default delays, timeouts, retry policies, recognition defaults.

### Editor

Font, theme, autocomplete, indentation, formatting, keyboard shortcuts.

### Debugging

Debugger settings, error screenshots, log levels.

### Performance

Worker limits, CPU usage policies, preview priorities, recognition settings.

### Security and Privacy

Trusted scripts, permissions, retention, diagnostics.

### Updates

Check for updates, download settings, update preferences.

Support configuration import/export, validation, and restoration of defaults.

# 21. LOGGING, MONITORING, AND DIAGNOSTICS

Implement structured logging.

Each log entry should include relevant context:

- Timestamp.
- Log level.
- Device ID.
- Script ID.
- Task ID.
- Event type.
- Message.
- Error details.

Provide filters for devices, scripts, severity, and time.

Support:

- Live console.
- Searchable logs.
- Clear/export logs.
- Failure screenshots.
- Crash reports.
- Device connection diagnostics.
- ADB and scrcpy diagnostics.
- Dependency checks.
- Support bundle export with sensitive-data redaction.

Monitoring should not consume excessive resources itself.

# 22. WINDOWS INSTALLATION AND DISTRIBUTION

Create two official distribution formats:

## A. Windows installer

A professional installation package that:

- Installs application files.
- Provides Start Menu integration.
- Supports uninstall.
- Includes necessary runtime dependencies.
- Preserves user projects during upgrades.

## B. Portable version

A portable ZIP or directory-based application that can be extracted and run.

## Bundled dependencies

Where licensing and compatibility permit, include:

- Python runtime.
- Required Python packages.
- PySide6 / Qt components.
- Qt WebEngine resources.
- Monaco assets.
- ADB platform tools.
- scrcpy components.
- Required media and OCR dependencies.

The user should not be required to install Python manually.

## First-run setup

Provide a setup wizard that:

1. Checks dependencies.
2. Verifies ADB.
3. Detects connected phones.
4. Explains USB debugging authorization.
5. Configures project storage.
6. Provides a test connection.
7. Opens a beginner tutorial or Script Studio.

## Updates

Support optional, user-controlled updates.

Include:

- Update checking.
- Signed or integrity-verified update packages.
- Release notes.
- Safe migrations.
- Project preservation.
- Rollback or recovery strategy.
- Offline core operation.

Do not require mandatory cloud authentication for basic features.

# 23. RECOMMENDED SOURCE CODE STRUCTURE

Use a modular organization similar to:

```text
android-automation-studio/
│
├── app/
│   ├── main.py
│   ├── bootstrap.py
│   │
│   ├── ui/
│   │   ├── shell/
│   │   ├── dashboard/
│   │   ├── script_studio/
│   │   ├── device_manager/
│   │   ├── task_manager/
│   │   ├── monitoring/
│   │   ├── settings/
│   │   ├── widgets/
│   │   └── themes/
│   │
│   ├── editor/
│   │   ├── bridge/
│   │   ├── language_support/
│   │   └── visual_tools/
│   │
│   ├── devices/
│   │   ├── adb/
│   │   ├── discovery/
│   │   ├── connection/
│   │   └── controls/
│   │
│   ├── streaming/
│   │   ├── scrcpy/
│   │   ├── decoding/
│   │   ├── rendering/
│   │   └── capture/
│   │
│   ├── automation/
│   │   ├── api/
│   │   ├── runtime/
│   │   ├── workers/
│   │   ├── vision/
│   │   ├── ocr/
│   │   ├── recorder/
│   │   ├── debugger/
│   │   └── recovery/
│   │
│   ├── scheduling/
│   ├── projects/
│   ├── storage/
│   ├── security/
│   ├── diagnostics/
│   └── updates/
│
├── editor_web/
│   ├── src/
│   ├── assets/
│   └── build/
│
├── examples/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── performance/
│
├── packaging/
├── docs/
│
├── pyproject.toml
├── README.md
└── LICENSE
```

Adapt the structure when justified. Avoid unnecessary abstraction and circular dependencies.

# 24. DEVELOPMENT ROADMAP

Implement the application in controlled, testable phases.

## Phase 0 — Architecture and Technical Proofs of Concept

Before large-scale development:

- Verify PySide6 and Qt WebEngine integration.
- Embed Monaco and test QWebChannel messaging.
- Detect Android phones using ADB.
- Launch and control scrcpy.
- Prototype embedded video streaming.
- Validate screenshots and coordinate transformation.
- Test independent workers on two phones.
- Evaluate packaging and licensing constraints.

Document major risks and select practical integration approaches.

**Gate:** Critical architectural integrations must be demonstrated or have documented fallback plans.

## Phase 1 — Application Foundation

Develop:

- Main PySide6 window.
- Navigation system.
- Theme system.
- Dockable workspace foundation.
- Settings infrastructure.
- Device discovery.
- Basic ADB connection management.

**Gate:** Program starts reliably and detects connected devices.

## Phase 2 — Phone Preview and Control

Develop:

- Screen streaming.
- Embedded previews.
- Preview grid.
- Detachable previews.
- Tap and swipe controls.
- Coordinate mapping.
- Screenshot capture.

**Gate:** Users can view and control a phone reliably from inside the application.

## Phase 3 — Monaco Script Studio

Develop:

- Editor embedding.
- QWebChannel bridge.
- Project explorer.
- Script saving.
- Automation toolbar.
- Screenshot insertion.
- Image asset management.

**Gate:** Users can capture a phone image and insert its reference as valid Python.

## Phase 4 — Automation Runtime

Develop:

- Python script workers.
- Device contexts.
- Basic click/swipe functions.
- Image recognition.
- Wait and exists.
- Cancellation.
- Per-device logs.

**Gate:** A real Python script detects and taps an Android screen target.

## Phase 5 — Multi-Device Execution

Develop:

- Shared-script mode.
- Independent-script mode.
- Worker isolation.
- Device routing.
- Group controls.
- Independent failure handling.

**Gate:** Two or more connected phones run appropriate scripts without command crossover.

## Phase 6 — Advanced Recognition and Recorder

Develop:

- OCR.
- Color/pixel recognition.
- Optional Android UI inspection.
- Image matching settings.
- Visual match tester.
- Recording.
- Generated Python editing.
- Replay.

**Gate:** Users can record a workflow, improve it with image matching, and replay it.

## Phase 7 — Debugger and Recovery

Develop:

- Breakpoints.
- Stepping.
- Variables.
- Call stacks.
- Action testing.
- Failure screenshots.
- Retry policies.
- Safe checkpoints.
- Recovery logs.

**Gate:** Users can debug real device scripts and safely handle an expected failure.

## Phase 8 — Task and Game Management

Develop:

- Task queues.
- Scheduler.
- Priorities.
- App switching.
- Repeating workflows.
- Task persistence.
- Multi-phone coordination.

**Gate:** A phone completes a scheduled sequence across multiple Android applications.

## Phase 9 — Advanced GUI and Projects

Develop:

- Layout presets.
- Full customization.
- Backups.
- Version history.
- Git integration where enabled.
- Project import/export.
- Tutorials.
- UX polishing.

**Gate:** Projects are portable and layouts restore correctly.

## Phase 10 — Optimization and Release

Develop:

- Performance benchmarking.
- Multi-device stress testing.
- Security improvements.
- Diagnostics.
- Dependency bundling.
- Installer.
- Portable release.
- Update mechanism.
- Documentation.

**Gate:** The application can be installed on a clean compatible Windows environment and pass its release tests.

# 25. TESTING STRATEGY

Create automated tests throughout development.

## Unit tests

Cover:

- Coordinate conversion.
- Image matching wrappers.
- Recognition result structures.
- Device selection.
- Script API validation.
- Task state transitions.
- Retry policies.
- Configuration serialization.
- Project import/export.

## Integration tests

Cover:

- ADB communication.
- Monaco/Python bridge.
- Video frame handling.
- Script worker IPC.
- Scheduler/worker coordination.
- Debugger integration.
- Database persistence.

## End-to-end tests

Verify these scenarios:

1. Connect an Android phone through USB.
2. Connect a second phone.
3. Display live previews for both.
4. Capture an image from Phone 1.
5. Insert an image-based click into Python.
6. Execute the script on Phone 1.
7. Execute the same script independently on Phone 2.
8. Run different scripts on both phones.
9. Simulate image-match failure and verify recovery.
10. Disconnect a phone and verify safe handling.
11. Set a breakpoint and inspect Python variables.
12. Record touch actions and generate editable code.
13. Schedule a multi-game workflow.
14. Save, export, and restore a project.
15. Restart the app and restore the workspace.
16. Install and launch a packaged Windows build.

Use emulators or mock devices for automated coverage where possible, and real Android phones for hardware validation.

## Performance tests

Measure real resource usage with progressively larger device counts.

Test:

- Idle application.
- One active phone.
- Several active phones.
- Multiple video streams.
- Parallel image recognition.
- Long-running tasks.
- Disconnection and reconnection.
- Repeated project opening and closing.

Document actual hardware, device models, FPS, and observed limits.

Do not fabricate benchmark results.

# 26. QUALITY AND ACCEPTANCE CRITERIA

The product is not complete simply because every page exists.

A feature is complete only when:

- Its interface works.
- Its backend behavior works.
- It handles expected errors.
- Its state is persisted where required.
- Its functionality is tested.
- Its documentation is available.

## Essential product acceptance criteria

- The GUI remains responsive during automation.
- Multi-device actions consistently target the correct device.
- Shared scripts use independent execution contexts.
- Users can select screenshot regions visually.
- Generated scripts contain valid Python.
- Image previews do not corrupt code.
- Device previews correctly map mouse gestures to Android coordinates.
- Script failures produce actionable diagnostics.
- Recovery does not blindly repeat unsafe actions.
- Device disconnection does not crash the whole application.
- Saved projects reopen correctly.
- User layouts restore after restart.
- The installer bundles required dependencies.
- Offline core functionality works.
- Security limitations are disclosed accurately.

All major visual controls must either function or be clearly marked as unavailable during phased development.

Do not hide incomplete functionality behind fake success messages.

# 27. REQUIRED DOCUMENTATION

Produce:

- Architecture document.
- Technology decision records.
- Installation guide.
- First-run guide.
- Device connection guide.
- User manual.
- Script API documentation.
- Image capture tutorial.
- Recorder tutorial.
- Debugging tutorial.
- Multi-device tutorial.
- Task scheduling guide.
- Troubleshooting guide.
- Developer contribution guide.
- Test instructions.
- Release and packaging instructions.

Include complete working code examples.

# 28. EXPECTED FINAL DELIVERABLES

Deliver:

1. Complete source code.
2. Modular Python backend.
3. Working PySide6 GUI.
4. Integrated Monaco script editor.
5. Working ADB device management.
6. Integrated Android screen previews.
7. SikuliX-style automation API.
8. Screenshot and image recognition tools.
9. Visual recorder.
10. Multi-device script execution.
11. Professional Python debugger.
12. Game and task scheduler.
13. Error recovery system.
14. Project management and backups.
15. Settings, security, and performance tools.
16. Automated tests and test results.
17. Windows installer.
18. Portable Windows release.
19. Documentation and examples.
20. Release notes and known limitations.

Do not report an unbuilt or untested executable as successfully delivered.

# 29. INSTRUCTIONS FOR HOW TO DEVELOP THIS PROJECT

Follow these rules strictly.

### Rule 1 — Do not skip architecture

Before coding, produce a clear technical design.

### Rule 2 — Respect confirmed choices

The fundamental architecture is Python + PySide6, with Monaco embedded through Qt WebEngine and QWebChannel.

Do not replace these choices without a specific documented technical blocker.

### Rule 3 — Build real features

No decorative-only controls, simulated connections, or hardcoded fake execution results presented as production functionality.

### Rule 4 — Work incrementally

Implement one coherent phase at a time. Integrate and test before continuing.

### Rule 5 — Explain engineering decisions

When alternatives exist, compare them based on reliability, maintainability, resource consumption, and actual project requirements.

### Rule 6 — Maintain code quality

Use type hints, meaningful names, modular interfaces, structured logs, clear error handling, and appropriate tests.

### Rule 7 — Prioritize reliability

Correct device targeting, stable execution, safe stopping, and failure recovery are more important than visual effects.

### Rule 8 — Be transparent

If a feature is incomplete, platform-limited, or untested, describe its actual status.

### Rule 9 — Do not invent results

Never claim an integration, build, or test passed without actually verifying it.

### Rule 10 — Preserve user work

Protect projects, images, scripts, settings, and backups during development and updates.

### Rule 11 — Minimize unnecessary dependencies

Prefer well-maintained, documented technologies and justify additional frameworks.

### Rule 12 — Continue from previous implementation

For every new development phase, inspect the existing project and avoid rewriting working modules unnecessarily.

# 30. YOUR FIRST RESPONSE AND FIRST DEVELOPMENT TASK

Begin by creating a **professional engineering blueprint** for Android Automation Studio.

Your first response must include:

1. **Requirements audit:** Confirm coverage of all product features and identify any inconsistencies.
2. **Architecture:** Define the complete application structure and module boundaries.
3. **Technology specification:** Recommend compatible dependency choices and explain key integration risks.
4. **Embedded scrcpy plan:** Explain how live Android previews will work inside PySide6, including video decoding, input, and fallbacks.
5. **Monaco integration plan:** Explain Qt WebEngine, QWebChannel communication, Python language assistance, and image decorations.
6. **Automation runtime design:** Explain workers, script contexts, IPC, cancellation, and device routing.
7. **Scripting API contract:** Define public functions, types, exceptions, and naming conventions.
8. **Database and project schemas:** Define how scripts, images, devices, schedules, and settings are organized.
9. **UI/UX blueprint:** Describe each workspace, navigation flow, panels, actions, and reusable components.
10. **Development plan:** Produce milestones, dependencies, technical risks, test plans, and acceptance criteria.

Then begin **Phase 0: Architecture and technical proofs of concept** using real source files and tests.

For each phase, provide:

- Implemented features.
- Source files created or modified.
- How to run and test the code.
- Test results actually obtained.
- Remaining limitations.
- Next implementation tasks.

Do not attempt to hide the complexity of the project by producing one enormous unmaintainable Python script.

Do not ask the user to choose technologies or features that have already been confirmed in this specification.

Make reasonable decisions for unspecified technical details, document them, and ask a question only if a truly blocking requirement cannot be resolved safely.

**Ultimate objective:** Build a complete, maintainable, professional-grade Android Automation Studio that combines the convenience of SikuliX, the phone connectivity of scrcpy/ADB, the editing capabilities of a Python IDE, and reliable multi-phone automation management in one polished Windows desktop application.

**Start with the engineering blueprint and Phase 0 implementation.**