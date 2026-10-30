# Embedded Android video integration

This stage implements a real video transport and H.264 decoder, independently
of the Qt preview widget. It does not generate live-looking video from Android
screenshots. Physical Android streaming and Windows compatibility remain
unverified until the hardware procedure below passes.

## Pinned contract

The client implements **scrcpy server 3.1**, video-only, H.264, default Android
display. The exact official `scrcpy-server-v3.1` artifact must have SHA-256
`958f0944a62f23b1f33a16e9eb14844c1a04b882ca175a738c16d23cb22b86c0`.
The session checks that digest for both the normal local artifact and a custom
`STUDIO_SCRCPY_SERVER` path. It rejects another version rather than silently
misparse a changed protocol. `tools/fetch_scrcpy.py` obtains the pinned artifact.

The implementation follows these official versioned sources:

- [Options.java](https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/Options.java): server arguments.
- [DesktopConnection.java](https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/device/DesktopConnection.java): socket naming, dummy byte and device metadata.
- [Streamer.java](https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/Streamer.java): codec metadata and packet framing.
- [demuxer.c](https://github.com/Genymobile/scrcpy/blob/v3.1/app/src/demuxer.c): combining H.264 configuration with the following media packet.
- [SurfaceEncoder.java](https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/video/SurfaceEncoder.java): encoder configuration and repeated-frame request.
- [SHA256SUMS.txt](https://github.com/Genymobile/scrcpy/releases/download/v3.1/SHA256SUMS.txt): official release checksums.

No native scrcpy GUI window is reparented. This client does not require the
desktop scrcpy executable. The existing external-window adapter remains a
separate optional fallback.

## Session lifecycle

Each serial gets its own background thread, random 31-bit session ID, generated
remote JAR path, local ADB TCP forward, Android server shell child, socket,
decoder, status and latest-frame mailbox. Commands always use `adb -s SERIAL`.

1. Verify the local server artifact, then push it to
   `/data/local/tmp/aas-scrcpy-<session>.jar`.
2. Allocate `adb -s SERIAL forward tcp:0 localabstract:scrcpy_<8hex-session>`.
   ADB returns the exact allocated port; the client does not guess a fixed port.
3. Start the matching server using generated/validated arguments:

   ```text
   adb -s SERIAL shell CLASSPATH=/data/local/tmp/aas-scrcpy-SESSION.jar
       app_process / com.genymobile.scrcpy.Server 3.1 scid=SESSION
       video=true audio=false control=false video_codec=h264
       tunnel_forward=true max_size=1280 max_fps=30 video_bit_rate=8000000
       send_device_meta=true send_codec_meta=true send_frame_meta=true
       send_dummy_byte=true cleanup=true log_level=info
   ```

   The display above is wrapped for readability; implementation passes argv,
   never untrusted shell fragments. Scrcpy receives one video socket and no
   audio or control socket. Touch/key input uses the existing validated ADB
   adapter, so the server cannot independently control the device.
4. Connect only to the owned loopback forward. Retry early-forward EOF while
   Android is creating its abstract socket. Validate the first dummy byte.
5. Read the fixed 64-byte UTF-8 device name, big-endian H.264 codec ID/encoded
   width/height, then length-delimited video packets. The high two PTS bits mark
   configuration and keyframes. Bounds cover payloads, dimensions and partial
   records. Startup must yield a decoded frame within ten seconds after
   metadata; configuration packets never extend that deadline. Socket timeouts
   allow cancellation. Established unchanged screens may remain idle without
   being falsely treated as a malformed packet.
6. Merge codec configuration into the next media packet and decode using
   **PyAV 14.2.0** / FFmpeg. Convert decoded frames to owned packed RGB bytes.
   Qt receives only the most recent frame when its render timer polls, so a
   slow widget cannot accumulate a frame/event FIFO.
7. On stop, discard the latest frame immediately and close the socket to wake
   reads. Cleanup terminates only the owned local shell child, removes only its
   allocated forward and attempts removal of only its generated remote file.
   Neither `adb kill-server` nor `forward --remove-all` is used. Cleanup errors
   remain visible; physical-disconnect cleanup cannot promise a remote shell
   command succeeded while transport is absent.

Start/stop/status/close requests do not perform ADB/decode work on the GUI
thread. `close(timeout=0)` reports whether cleanup has finished; the window can
defer exit while continuing to process Qt events. A still-stopping serial
cannot start another session. A failed phone does not stop other previews.
Reconnection is explicit and creates a new session; it does not resume scripts
or replay input automatically.

## Coordinates, orientation and quality

Encoded video size is **not** necessarily Android touch-coordinate size.
`max_size` scales the stream. Each `VideoFrame` therefore includes encoded
`width/height`, original `source_width/source_height`, serial, sequence,
monotonic arrival time, optional observed Android orientation, and immutable
RGB bytes. The preview fits the image with letterboxes; its inverse transform
uses original dimensions for ADB input. Screenshot/crop tools capture original
resolution rather than mistake a scaled video frame for a full-resolution PNG.

The background session reads actual screenshot dimensions plus observed
`dumpsys input` orientation initially, on encoded-size changes, and at a
two-second checkpoint while frames arrive. This detects same-aspect source
resolution changes even when the encoder stays at its size cap, and exposes
180-degree rotation changes. Unsupported orientation metadata remains `None`.
Encoded/source aspect must agree within codec alignment tolerance; otherwise
the session fails instead of guessing input coordinates. Observed geometry
changes invalidate gestures in the UI. These checks have transport/encoder
latency and cannot make Android display state and a later ADB action atomic.

FPS (1–120), bitrate (100 kbit/s–100 Mbit/s), and maximum dimension
(256–4096) are validated server options. Changing them requires an explicit
stream restart. They are requests to Android's encoder, not measured promises.
The server rounds maximum size to a multiple of eight. It requests repeated
frames after 100 ms, but codec behavior varies; if a frame exceeds the UI's
freshness deadline, obtain a fresh screenshot or restart before controlling it.
No hardware FPS, latency or device-capacity benchmark has been claimed.

## Automated evidence

`tests/test_stream_protocol.py` covers fragmented reads, metadata/packet flags,
size limits, wrong codec, partial timeouts, legitimate idle periods, cancellation
and EOF. `tests/test_stream_decoder.py` uses actual libx264/FFmpeg H.264 encoding
and PyAV decoding, configuration separation, RGB pixels and changing dimensions.
`tests/test_stream_session.py` sends fragmented scrcpy packets through real
local socket pairs and exercises transport → protocol → decoder → original
coordinate metadata, disconnect and owned-resource cleanup. Android execution
and ADB subprocess results in that test are explicitly fixtures.
`tests/test_stream_manager.py` covers independent serial mailboxes, worker cap,
latest-only replacement, stop invalidation, error isolation and cleanup gating.
The cloud command sandbox blocks local IPC socket writes; these integration
checks use its supported escalated execution mode.

## Real-device acceptance procedure

1. On a supported Windows x64 or Linux desktop, install the locked dependencies
   and pinned server, and connect an authorized phone. Record OS, Python/Qt,
   ADB/server/PyAV versions, phone model, Android version and USB/Wi-Fi transport.
2. Confirm `adb devices -l` identifies the intended serial. Start its embedded
   preview and verify continuously changing Android content is real video.
3. Change FPS/bitrate/max-size with explicit restart. Measure actual decoded
   FPS, latency and resource use rather than infer them from requested settings.
4. Tap screen landmarks at corners/center, reject letterboxes, then verify
   double tap, long press, swipe/drag, Home and Back on the selected phone.
   Check original source coordinates when the video is scaled.
5. Rotate 90/180/270 degrees and change device resolution, including a change
   with the same aspect ratio. Ensure gesture cancellation and correct mapping.
6. Start a second phone independently. Compare distinct content and serials;
   controls on either phone must not cross over. Disconnect one during video
   and while sending input; its status/frame must invalidate while the other
   remains usable. Reconnect explicitly and confirm no input/script replay.
7. Capture a full-resolution image, select/crop a region, save its asset and
   insert a valid Python image string. Test it against a fresh original capture
   and inspect match score/bounds/target location. Scores are not probabilities.
8. Stop and restart repeatedly; close the app during startup, capture and active
   streams. Inspect owned forwards/server sessions for cleanup, including the
   disconnected-device case. Preserve unrelated ADB sessions.

These hardware steps, clean Windows behavior and codec/device compatibility
remain acceptance gates. Passing synthetic H.264/local-socket tests does not
establish any of them.
