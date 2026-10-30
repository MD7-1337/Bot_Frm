"""Owned video-only scrcpy 3.1 session over a serial-specific ADB forward.

Source contract:
https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/Options.java
https://github.com/Genymobile/scrcpy/blob/v3.1/server/src/main/java/com/genymobile/scrcpy/device/DesktopConnection.java

Only the exact generated forward, remote JAR, local ADB shell child and socket
are cleaned up. No global adb kill-server / forward --remove-all is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from typing import Callable

from app.devices.adb import AdbClient, AdbError, validate_serial
from app.streaming.decoder import H264Decoder
from app.streaming.protocol import ScrcpyProtocol, StreamCancelled

SERVER_VERSION = "3.1"
SERVER_SHA256 = "958f0944a62f23b1f33a16e9eb14844c1a04b882ca175a738c16d23cb22b86c0"
SOURCE_GEOMETRY_CHECK_SECONDS = 2.0


class StreamError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StreamOptions:
    max_fps: int = 30
    bitrate: int = 8_000_000
    max_size: int = 1280

    def __post_init__(self):
        for name, low, high in (("max_fps", 1, 120), ("bitrate", 100_000, 100_000_000), ("max_size", 256, 4096)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")


@dataclass(frozen=True, slots=True)
class VideoFrame:
    serial: str
    rgb: bytes
    width: int
    height: int
    source_width: int
    source_height: int
    captured_at: float
    sequence: int
    orientation: int | None = None


class ScrcpySession:
    """Run only on a background thread; ``request_stop`` is nonblocking."""

    def __init__(self, adb: AdbClient, serial: str, server_path: Path, options: StreamOptions,
                 on_frame: Callable[[VideoFrame], None], on_state: Callable[[str, str | None], None]):
        self.adb = adb
        self.serial = validate_serial(serial)
        self.server_path = Path(server_path)
        self.options = options
        self.on_frame = on_frame
        self.on_state = on_state
        self.cancelled = threading.Event()
        self.scid = secrets.randbelow(0x7FFFFFFE) + 1
        self.remote_path = f"/data/local/tmp/aas-scrcpy-{self.scid:08x}.jar"
        self.forward_port: int | None = None
        self.process = None
        self.connection = None
        self._socket_lock = threading.Lock()
        self._logs: list[str] = []
        self._log_lock = threading.Lock()
        self._log_thread = None
        self._pushed = False

    def _command(self, *args: str) -> bytes:
        # These arguments are generated internally; no user-provided remote
        # shell command, path or option fragment is accepted by this boundary.
        return self.adb._device(self.serial, *args)

    def _checkpoint(self):
        if self.cancelled.is_set():
            raise StreamCancelled("Stream stop requested")

    def request_stop(self):
        self.cancelled.set()
        with self._socket_lock:
            connection = self.connection
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()

    def server_arguments(self) -> list[str]:
        return [self.adb.executable, "-s", self.serial, "shell",
                f"CLASSPATH={self.remote_path}", "app_process", "/", "com.genymobile.scrcpy.Server", SERVER_VERSION,
                f"scid={self.scid:08x}", "log_level=info", "video=true", "audio=false", "control=false",
                "video_codec=h264", "tunnel_forward=true", f"max_size={self.options.max_size}",
                f"max_fps={self.options.max_fps}", f"video_bit_rate={self.options.bitrate}",
                "send_device_meta=true", "send_codec_meta=true", "send_frame_meta=true", "send_dummy_byte=true", "cleanup=true"]

    def _read_logs(self):
        try:
            for line in iter(lambda: self.process.stdout.readline(4096), b""):
                with self._log_lock:
                    self._logs.append(line.decode("utf-8", errors="replace").strip()[:1000])
                    del self._logs[:-12]
        except (OSError, ValueError):
            pass

    def _last_log(self) -> str:
        with self._log_lock:
            return " | ".join(self._logs)[-2000:]

    def _open(self):
        self._checkpoint()
        if not self.server_path.is_file():
            raise StreamError("scrcpy 3.1 server missing. Run tools/fetch_scrcpy.py or set STUDIO_SCRCPY_SERVER.")
        if self.server_path.stat().st_size > 2_000_000 or hashlib.sha256(self.server_path.read_bytes()).hexdigest() != SERVER_SHA256:
            raise StreamError("scrcpy server integrity/version mismatch; the exact official v3.1 server is required")
        self._command("push", str(self.server_path), self.remote_path)
        self._pushed = True
        self._checkpoint()
        raw_port = self._command("forward", "tcp:0", f"localabstract:scrcpy_{self.scid:08x}").decode("ascii").strip()
        if not raw_port.isdecimal() or not 1 <= int(raw_port) <= 65535:
            raise StreamError("ADB did not return a valid dynamically allocated local forward port")
        self.forward_port = int(raw_port)
        self._checkpoint()
        self.process = subprocess.Popen(self.server_arguments(), stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        self._log_thread = threading.Thread(target=self._read_logs, name=f"scrcpy-log-{self.serial}", daemon=True)
        self._log_thread.start()
        deadline = time.monotonic() + 10
        last_error = None
        while time.monotonic() < deadline:
            self._checkpoint()
            if self.process.poll() is not None:
                raise StreamError("scrcpy server exited before connection: " + self._last_log())
            try:
                connection = socket.create_connection(("127.0.0.1", self.forward_port), timeout=0.25)
                connection.settimeout(0.25)
                with self._socket_lock:
                    self.connection = connection
                # ADB forwards may connect before Android's abstract socket is
                # listening. Validate the dummy byte before committing to it.
                while True:
                    self._checkpoint()
                    try:
                        dummy = connection.recv(1)
                        break
                    except socket.timeout:
                        if time.monotonic() >= deadline:
                            raise StreamError("Timed out waiting for the scrcpy forward-tunnel handshake")
                        if self.process.poll() is not None:
                            raise StreamError("scrcpy server exited during handshake: " + self._last_log())
                if dummy != b"\x00":
                    connection.close()
                    with self._socket_lock:
                        if self.connection is connection:
                            self.connection = None
                    last_error = "Server socket is not ready"
                else:
                    self._checkpoint()
                    return
            except OSError as error:
                last_error = str(error)
                try:
                    connection.close()
                except (UnboundLocalError, OSError):
                    pass
            self.cancelled.wait(0.1)
        raise StreamError(f"Timed out opening scrcpy video channel: {last_error}. {self._last_log()}")

    @staticmethod
    def _compatible_dimensions(encoded: tuple[int, int], source: tuple[int, int]) -> bool:
        width, height = encoded
        swidth, sheight = source
        # MediaCodec rounds to aligned dimensions. Permit an eight-pixel error
        # per axis, never a portrait/landscape coordinate-space mismatch.
        expected_height = width * sheight / swidth
        return abs(height - expected_height) <= max(8, 8 * sheight / swidth)

    def run(self):
        decoder = None
        failed = False
        try:
            self.on_state("starting", None)
            self._open()
            # _open already consumed the forward-tunnel dummy byte.
            reader = ScrcpyProtocol(self.connection, self.cancelled, expect_dummy=False)
            reader.read_header()
            decoder = H264Decoder()
            encoded_geometry = None
            source_geometry = None
            source_orientation = None
            last_geometry_check = 0.0
            sequence = 0
            while True:
                self._checkpoint()
                # Startup must produce an actual decoded frame within the
                # protocol deadline. Config-only or unusable media cannot leave
                # the UI stuck in "starting" forever. Established static video
                # may then idle normally until cancellation.
                packet = reader.read_packet(allow_idle=sequence > 0)
                for decoded in decoder.decode(packet):
                    self._checkpoint()
                    geometry = (decoded.width, decoded.height)
                    if geometry != encoded_geometry or time.monotonic() - last_geometry_check >= SOURCE_GEOMETRY_CHECK_SECONDS:
                        # Codec metadata describes encoded size, NOT input
                        # coordinate space when max_size scales the video.
                        info = self.adb.screen_info(self.serial)
                        self._checkpoint()
                        source_geometry = (info.width, info.height)
                        source_orientation = info.orientation
                        if not self._compatible_dimensions(geometry, source_geometry):
                            raise StreamError("Screen orientation changed during video negotiation; restart the preview to remap safely")
                        encoded_geometry = geometry
                        last_geometry_check = time.monotonic()
                    sequence += 1
                    output = VideoFrame(self.serial, decoded.rgb, *geometry, *source_geometry, time.monotonic(), sequence, source_orientation)
                    self.on_frame(output)
                    self.on_state("streaming", None)
        except StreamCancelled:
            self.on_state("stopping", None)
        except Exception as error:
            if not self.cancelled.is_set():
                failed = True
                self.on_state("failed", f"{type(error).__name__}: {error}"[:2500])
        finally:
            self.request_stop()
            if decoder is not None:
                decoder.close()
            cleanup_errors = self._cleanup()
            if cleanup_errors:
                self.on_state("failed", "Stream cleanup: " + "; ".join(cleanup_errors))
            elif not failed:
                self.on_state("stopped", None)

    def _cleanup(self) -> list[str]:
        errors = []
        if self.process is not None:
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as error:
                errors.append(f"owned server shell: {error}")
            if self.process.stdout is not None:
                self.process.stdout.close()
        if self._log_thread is not None:
            self._log_thread.join(timeout=0.5)
        if self.forward_port is not None:
            try:
                self._command("forward", "--remove", f"tcp:{self.forward_port}")
            except AdbError as error:
                errors.append(f"remove own forward: {error}")
        if self._pushed:
            try:
                self._command("shell", "rm", "-f", self.remote_path)
            except AdbError as error:
                errors.append(f"remove own remote server: {error}")
        return errors
