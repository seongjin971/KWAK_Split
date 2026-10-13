"""Retained Windows PCM output with device-clock pause/resume and bounded queues.

Buffer storage remains owned until waveOut returns it. Session generations keep
cancelled preparation workers from writing to or resetting a newer playback.
"""
from __future__ import annotations

import ctypes as c
import os
import threading
import time

from backend.audio_processing.spectrum import SAMPLE_RATE


class WaveFormat(c.Structure):
    _pack_ = 1
    _fields_ = [("format", c.c_uint16), ("channels", c.c_uint16),
                ("rate", c.c_uint32), ("bytes_per_second", c.c_uint32),
                ("alignment", c.c_uint16), ("bits", c.c_uint16), ("extra", c.c_uint16)]


class WaveHeader(c.Structure):
    _fields_ = [("data", c.c_void_p), ("length", c.c_uint32), ("recorded", c.c_uint32),
                ("user", c.c_size_t), ("flags", c.c_uint32), ("loops", c.c_uint32),
                ("next", c.c_void_p), ("reserved", c.c_size_t)]


class TimeValue(c.Union):
    _fields_ = [("count", c.c_uint32), ("padding", c.c_ubyte * 8)]


class WaveTime(c.Structure):
    _fields_ = [("kind", c.c_uint32), ("value", TimeValue)]


class WaveOutDriver:
    """Small WinMM binding; all calls are serialized by WaveOutputDevice."""
    def __init__(self):
        self.api = c.WinDLL("winmm")
        self.handle = c.c_void_p()
        signatures = {
            "waveOutOpen": [c.POINTER(c.c_void_p), c.c_uint32, c.POINTER(WaveFormat),
                            c.c_size_t, c.c_size_t, c.c_uint32],
            "waveOutGetPosition": [c.c_void_p, c.POINTER(WaveTime), c.c_uint32],
            "waveOutGetErrorTextW": [c.c_uint32, c.c_wchar_p, c.c_uint32],
        }
        for name in ("waveOutPause", "waveOutRestart", "waveOutReset", "waveOutClose"):
            signatures[name] = [c.c_void_p]
        for name in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
            signatures[name] = [c.c_void_p, c.POINTER(WaveHeader), c.c_uint32]
        for name, args in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, c.c_uint32
        fmt = WaveFormat(1, 2, SAMPLE_RATE, SAMPLE_RATE * 4, 4, 16, 0)
        self.check(self.api.waveOutOpen(c.byref(self.handle), 0xFFFFFFFF,
                                       c.byref(fmt), 0, 0, 0), "open")
        self._counter = self._wrap = self._kind = 0

    def check(self, result, operation):
        if result:
            text = c.create_unicode_buffer(256)
            self.api.waveOutGetErrorTextW(result, text, len(text))
            raise OSError(f"Audio output {operation} failed ({result}): {text.value}")

    def call(self, name):
        self.check(getattr(self.api, "waveOut" + name)(self.handle), name.lower())

    def reset(self):
        self.call("Reset")
        self._counter = self._wrap = self._kind = 0

    def position(self):
        value = WaveTime(); value.kind = 2  # TIME_SAMPLES, with documented fallback.
        self.check(self.api.waveOutGetPosition(self.handle, c.byref(value), c.sizeof(value)), "clock")
        count = value.value.count
        if value.kind != self._kind:
            self._counter = self._wrap = 0; self._kind = value.kind
        if count < self._counter and self._counter - count > 0x80000000:
            self._wrap += 1 << 32
        self._counter = count
        total = count + self._wrap
        if value.kind == 2:return total
        if value.kind == 4:return total / 4  # TIME_BYTES
        if value.kind == 1:return total * SAMPLE_RATE / 1000  # TIME_MS
        raise OSError(f"Unsupported audio clock format: {value.kind}")

    def write(self, pcm):
        storage = c.create_string_buffer(pcm)
        header = WaveHeader(data=c.addressof(storage), length=len(pcm))
        self.check(self.api.waveOutPrepareHeader(self.handle, c.byref(header), c.sizeof(header)), "prepare")
        try:
            self.check(self.api.waveOutWrite(self.handle, c.byref(header), c.sizeof(header)), "write")
        except Exception:
            self.api.waveOutUnprepareHeader(self.handle, c.byref(header), c.sizeof(header))
            raise
        return storage, header

    def done(self, block):return bool(block[1].flags & 1)  # WHDR_DONE

    def release(self, block):
        self.check(self.api.waveOutUnprepareHeader(self.handle, c.byref(block[1]),
                                                  c.sizeof(block[1])), "release")

    def close(self):
        if self.handle:
            self.call("Close")
            self.handle = c.c_void_p()


class WaveOutputDevice:
    """One device across playback sessions; a 120 ms queue stays paused when idle."""
    queue_seconds = .12

    def __init__(self, *, muted=False, driver=None):
        self._lock = threading.RLock()
        self._driver = driver or WaveOutDriver()
        self.muted = muted
        self._blocks = []
        self._generation = 0
        self._closed = False
        self.failed = False
        self._owner = None
        self.open_count = 1

    @property
    def handle(self):return self._driver.handle.value

    def _release_done(self):
        while self._blocks and self._driver.done(self._blocks[0]):
            self._driver.release(self._blocks[0])
            self._blocks.pop(0)

    def _reset(self):
        self._driver.reset()
        self._release_done()
        if self._blocks:
            raise OSError("The audio device did not release its reset buffers.")

    def begin(self):
        with self._lock:
            if self._closed or self.failed:raise OSError("Audio output is unavailable.")
            self._reset()
            if self._owner:self._owner.returncode = 0
            self._generation += 1
            self._driver.call("Pause")
            player = WaveOutputPlayer(self, self._generation)
            self._owner = player
            return player

    def close(self):
        with self._lock:
            if self._closed:return
            self._closed = True
            try:
                self._reset()
            finally:
                if self._owner:self._owner.returncode = 0
                self._driver.close()


class WaveOutputPlayer:
    """A session endpoint with the lifecycle interface used by AnalyzedPlayback."""
    pid = None  # It is a device session, never a subprocess PID.

    def __init__(self, device, generation):
        self.device, self.generation = device, generation
        self.stdin = self
        self.returncode = None
        self.error = ""
        self.paused = True
        self._eof = False
        self._written = 0
        self._position = 0.0
        self._wake = threading.Event()

    def _valid(self):
        return (self.returncode is None and not self.device._closed
                and self.generation == self.device._generation)

    def _fail(self, exc):
        self.error = str(exc); self.returncode = 1; self.device.failed = True
        self._wake.set()

    def position_seconds(self, force=False):
        with self.device._lock:
            if self._valid() and (force or not self.paused):
                try:
                    self._position = max(self._position,
                                         min(self._written, self.device._driver.position()) / SAMPLE_RATE)
                    self.device._release_done()
                except OSError as exc:self._fail(exc)
            return self._position

    def poll(self):
        with self.device._lock:
            if not self._valid():return self.returncode if self.returncode is not None else 0
            self.position_seconds()
            if self.returncode is None and self._eof and not self.device._blocks:
                self.returncode = 0
            return self.returncode

    @property
    def queued_seconds(self):
        return max(0, self._written / SAMPLE_RATE - self.position_seconds())

    def write(self, pcm):
        pcm = bytes(pcm)
        if len(pcm) % 4:raise ValueError("PCM must contain complete stereo frames.")
        while True:
            with self.device._lock:
                if not self._valid():raise BrokenPipeError("The prepared playback was replaced or closed.")
                if self.queued_seconds < self.device.queue_seconds:
                    try:
                        block = self.device._driver.write(bytes(len(pcm)) if self.device.muted else pcm)
                        self.device._blocks.append(block)
                        self._written += len(pcm) // 4
                        return len(pcm)
                    except OSError as exc:
                        self._fail(exc)
                        raise
            self._wake.wait(.003); self._wake.clear()

    def flush(self):pass

    def pause(self):
        with self.device._lock:
            if not self._valid():return False
            try:self.device._driver.call("Pause")
            except OSError as exc:
                self._fail(exc);return False
            self.paused = True
            self.position_seconds(force=True)
            return self.returncode is None

    def resume(self):
        with self.device._lock:
            if not self._valid():return False
            try:self.device._driver.call("Restart")
            except OSError as exc:
                self._fail(exc);return False
            self.paused = False
            self._wake.set()
            return True

    def close(self):
        # Closing stdin means EOF; keep the last buffers until the device drains.
        self._eof = True

    def terminate(self):
        with self.device._lock:
            if not self.device._closed and self.generation == self.device._generation:
                self.position_seconds()
                try:self.device._reset()
                except OSError as exc:self._fail(exc)
            if self.returncode is None:self.returncode = 0
            self._wake.set()

    kill = terminate

    def wait(self, timeout=None):
        deadline = time.monotonic() + (timeout if timeout is not None else 10)
        while self.poll() is None:
            if time.monotonic() >= deadline:
                from subprocess import TimeoutExpired
                raise TimeoutExpired("Windows audio output", timeout)
            time.sleep(.002)
        return self.returncode


def create_output_device():
    # Automated checks can exercise the real device/clock without audible tones.
    return WaveOutputDevice(muted=os.environ.get("SDL_AUDIODRIVER") == "dummy")
