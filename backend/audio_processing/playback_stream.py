"""Bounded PCM output, live controls and warm seeks through a retained player."""
from __future__ import annotations

from array import array
from collections import deque
from dataclasses import dataclass
import math
import os
import re
import subprocess
import sys
import threading
import time

from backend.audio_processing.spectrum import SAMPLE_RATE, SpectrumAnalyzer

_CLOCK = re.compile(rb"^\s*(-?\d+(?:\.\d+)?)\s+[A-Z]-[A-Z]:")
_CHUNK_BYTES = 1024  # One 256-frame filter block; keep live command pacing fine.
_PREPARE_BYTES = 4096  # Warm 23 ms before a seek handoff.


def _terminate(process, wait=True):
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    if wait:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


@dataclass(eq=False)
class DecoderStage:
    process: object
    controller: object = None
    eq_parameters: object = None
    mixer_parameters: object = None

    def update_eq(self, effects):
        if not self.controller or not self.eq_parameters:
            return False
        parameters = self.eq_parameters(effects)
        return parameters is not None and self.controller.submit(parameters)

    def update_mixer(self, stems):
        if not self.controller or not self.mixer_parameters:
            return False
        weights = self.mixer_parameters(stems)
        return weights is not None and self.controller.submit_mixer(weights)

    def close(self, wait=True):
        if self.controller:
            self.controller.close()
        _terminate(self.process, wait)
        if wait:
            self.process.stdout.close()
            if self.controller:
                self.controller.join()


@dataclass(frozen=True)
class PlaybackPosition:
    revision: int
    start_seconds: float
    duration_seconds: float
    tempo_ratio: float
    position_seconds: float
    seeking: bool


def _read_pcm(source, size=_CHUNK_BYTES):
    """Pipe reads may be partial; retain stereo-frame alignment at every handoff."""
    chunks = bytearray()
    while len(chunks) < size:
        data = source.read(size - len(chunks))
        if not data:
            break
        chunks.extend(data)
    return bytes(chunks[:len(chunks) // 4 * 4])


def _crossfade(old, new):
    """A 10 ms linear handoff limits clicks without increasing peak amplitude."""
    count = min(len(old), len(new), round(.01 * SAMPLE_RATE) * 4) // 4
    if count < 2:
        return new
    before, after = array("h"), array("h")
    before.frombytes(old[:count * 4]); after.frombytes(new)
    if sys.byteorder != "little":
        before.byteswap(); after.byteswap()
    for frame in range(count):
        mix = frame / (count - 1)
        for channel in (0, 1):
            i = frame * 2 + channel
            after[i] = round(before[i] * (1 - mix) + after[i] * mix)
    if sys.byteorder != "little":
        after.byteswap()
    return after.tobytes()


class AnalyzedPlayback(list):
    """FFplay stays first for completion tracking; seeks replace only decoding.

    One worker prepares the latest requested position. The relay switches only
    after real PCM is ready, keeping the player, output clock and spectrum tap.
    Rendered-WAV analysis has no player/factory and keeps its elapsed-file clock.
    """
    PREPARE_TIMEOUT_SECONDS = 3.0

    def __init__(self, decoder, player=None, *, decoder_factory=None, settings=None):
        stage = decoder if isinstance(decoder, DecoderStage) else DecoderStage(decoder)
        super().__init__([player, stage.process] if player else [stage.process])
        self._stage, self.player = stage, player
        self.spectrum = SpectrumAnalyzer()
        self._stop = threading.Event()
        self._started = time.monotonic()
        self._clock = None
        self._clock_lock = threading.Lock()
        self._sent_frames = 0
        self._last_pcm_frame = bytes(4)
        self._device_clock = getattr(player, "position_seconds", None)
        self.lookahead_seconds = (.12 if self._device_clock else .24 if stage.controller else .35)
        self.error = ""
        self._eq_error_reported = False
        self._state_lock = threading.RLock()
        self._factory = decoder_factory
        self._settings = dict(settings or {})
        self._seek_wake = threading.Event()
        self._request = self._ready = self._preparing = None
        self._retired = []
        self._accept_seeks = bool(player and decoder_factory)
        self.seek_revision = self.applied_seek_revision = self._failed_seek_revision = 0
        self._seek_error = ""
        # Entries map continuous OUTPUT time to discontinuous SOURCE time.
        self._timeline = deque([(0., 0, dict(self._settings))]) if settings else deque()
        self._threads = []
        if player and not self._device_clock:
            self._threads.append(threading.Thread(target=self._read_clock,
                                                  name="spectrum-clock", daemon=True))
        if self._factory:
            self._threads.append(threading.Thread(target=self._prepare_seeks,
                                                  name="playback-seek", daemon=True))
        self._threads.append(threading.Thread(target=self._relay, name="playback-pcm", daemon=True))
        if stage.controller:
            stage.controller.start()
        for thread in self._threads:
            thread.start()

    @property
    def decoder(self):
        return self._stage.process

    @property
    def eq_controller(self):
        return self._stage.controller

    def update_eq(self, effects):
        with self._state_lock:
            if self._stop.is_set() or not self._stage.update_eq(effects):
                return False
            self._settings["effects"] = effects
            if self._ready:
                self._ready[1].update_eq(effects)
        return True

    def update_mixer(self, stems):
        stems = tuple(stems)
        with self._state_lock:
            if self._stop.is_set() or not self._stage.update_mixer(stems):
                return False
            self._settings["stems"] = stems
            if self._ready:
                self._ready[1].update_mixer(stems)
        return True

    def take_eq_error(self):
        with self._state_lock:
            if self.eq_controller and self.eq_controller.error and not self._eq_error_reported:
                self._eq_error_reported = True
                return self.eq_controller.error
        return ""

    def seek(self, start_seconds, duration_seconds, **settings):
        """Nonblocking, latest-only request. Tk never waits for a decoder or ZMQ."""
        if not all(math.isfinite(v) for v in (start_seconds, duration_seconds)):
            return False
        if start_seconds < 0 or duration_seconds <= 0:
            return False
        with self._state_lock:
            if self._stop.is_set() or not self._accept_seeks or self.player.poll() is not None:
                return False
            self._settings.update(settings, start_seconds=start_seconds, duration_seconds=duration_seconds)
            self.seek_revision += 1
            self._request = self.seek_revision
            self._seek_error = ""
            self._seek_wake.set()
        return True

    def take_seek_error(self):
        with self._state_lock:
            error, self._seek_error = self._seek_error, ""
        return error

    def playback_position(self):
        clock = self.position_seconds()
        with self._state_lock:
            if not self._timeline:
                return None
            # Retain the audible entry plus a bounded lookahead of handoffs.
            while len(self._timeline) > 1 and self._timeline[1][0] <= clock:
                self._timeline.popleft()
            output_start, revision, settings = self._timeline[0]
            start, duration = settings["start_seconds"], settings["duration_seconds"]
            tempo = settings["effects"].tempo_ratio
            pending = self.seek_revision > max(revision, self._failed_seek_revision)
            position = start + min(duration, max(0., clock - output_start) * tempo)
            return PlaybackPosition(revision, start, duration, tempo, position, pending)

    def position_seconds(self):
        if self._device_clock:
            position = self._device_clock()
            with self._clock_lock:
                self._clock = (position, time.monotonic())
            return max(0., min(position, self._sent_frames / SAMPLE_RATE))
        now = time.monotonic()
        with self._clock_lock:
            clock = self._clock
        if clock is not None:
            position = clock[0] + max(0.0, now - clock[1])
        else:
            position = max(0.0, now - self._started - (.08 if self.player else 0))
        return max(0.0, min(position, self._sent_frames / SAMPLE_RATE))

    def spectrum_frame(self):
        return self.spectrum.frame_at(self.position_seconds())

    def pause(self):
        pause = getattr(self.player, "pause", None)
        return bool(pause and pause())

    def resume(self):
        resume = getattr(self.player, "resume", None)
        return bool(resume and resume())

    def _read_clock(self):
        stream = self.player.stderr
        pending = b""
        try:
            while not self._stop.is_set():
                chunk = os.read(stream.fileno(), 4096)
                if not chunk:
                    break
                pieces = re.split(rb"[\r\n]", pending + chunk)
                pending = pieces.pop()[-2048:]
                for line in pieces:
                    match = _CLOCK.match(line)
                    if match:
                        value = float(match.group(1))
                        if value >= 0:
                            with self._clock_lock:
                                self._clock = (value, time.monotonic())
        except (OSError, ValueError):
            pass
        finally:
            stream.close()

    def _prepare_seeks(self):
        try:
            while not self._stop.is_set():
                self._seek_wake.wait(.05)
                self._seek_wake.clear()
                with self._state_lock:
                    retired, self._retired = self._retired, []
                    # Finish one prepared handoff before preparing the latest
                    # pending position. Discarding every superseded preparation
                    # would starve audio changes throughout a fast held drag.
                    request = None if self._ready else self._request
                    if request:
                        self._request = None
                    settings = dict(self._settings)
                for stage in retired:
                    stage.close()
                if not request or self._stop.is_set():
                    continue
                stage = None
                try:
                    stage = self._factory(**settings)
                    with self._state_lock:
                        self._preparing = stage
                        cancelled = self._stop.is_set()
                    if cancelled:
                        continue
                    expired = threading.Event()
                    def expire(candidate=stage):
                        expired.set()
                        candidate.close(wait=False)
                    watchdog = threading.Timer(self.PREPARE_TIMEOUT_SECONDS, expire)
                    watchdog.daemon = True
                    watchdog.start()
                    try:
                        pcm = _read_pcm(stage.process.stdout, _PREPARE_BYTES)
                    finally:
                        watchdog.cancel()
                        watchdog.join(timeout=.2)
                    if expired.is_set():
                        raise TimeoutError("The requested audio position took too long to prepare.")
                    if not pcm:
                        raise RuntimeError("The requested position produced no audio.")
                    with self._state_lock:
                        if not self._stop.is_set():
                            # Include edits made while FFmpeg was opening the files.
                            stage.update_eq(self._settings["effects"])
                            stage.update_mixer(self._settings["stems"])
                            self._ready = (request, stage, pcm, settings)
                            stage = None  # Ownership passes to the relay.
                except Exception as exc:
                    with self._state_lock:
                        if not self._stop.is_set() and request == self.seek_revision:
                            self._failed_seek_revision = request
                            self._seek_error = str(exc)
                finally:
                    if stage:
                        stage.close()
                    with self._state_lock:
                        self._preparing = None
        finally:
            # Also covers close(wait=False) and a close racing with process start.
            with self._state_lock:
                stages, self._retired = self._retired, []
                if self._ready:
                    stages.append(self._ready[1]); self._ready = None
            for stage in stages:
                stage.close()

    def _handoff(self, pcm):
        # Only a seek needs a longer old-audio window. Ordinary live controls
        # retain fine 256-frame pacing instead of collecting a full 23 ms block.
        fade_bytes = round(.01 * SAMPLE_RATE) * 4
        if self._ready and len(pcm) < fade_bytes and not self._stop.is_set():
            pcm += _read_pcm(self.decoder.stdout, fade_bytes - len(pcm))
        with self._state_lock:
            if not self._ready or self._stop.is_set():
                return pcm
            revision, stage, incoming, settings = self._ready
            self._ready = None
            self._retired.append(self._stage)
            self._stage = stage
            self[1] = stage.process
            self._eq_error_reported = False
            clock = self.position_seconds()
            while len(self._timeline) > 1 and self._timeline[1][0] <= clock:
                self._timeline.popleft()
            self._timeline.append((self._sent_frames / SAMPLE_RATE, revision, settings))
            self.applied_seek_revision = revision
            if stage.controller:
                stage.controller.start()
            self._seek_wake.set()
        return _crossfade(pcm or self._last_pcm_frame * round(.01 * SAMPLE_RATE), incoming)

    def _relay(self):
        target = self.player.stdin if self.player else None
        try:
            while not self._stop.is_set():
                pcm = _read_pcm(self.decoder.stdout)
                # Switch AFTER pacing, discarding obsolete audio even if a newer
                # position arrived while waiting on the output clock.
                end = (self._sent_frames + max(len(pcm), _CHUNK_BYTES) // 4) / SAMPLE_RATE
                while end > self.position_seconds() + self.lookahead_seconds:
                    if self._stop.wait(.005):
                        return
                    if self.player and self.player.poll() is not None:
                        return
                pcm = self._handoff(pcm)
                if not pcm:
                    with self._state_lock:
                        seeking = self.seek_revision > max(self.applied_seek_revision, self._failed_seek_revision)
                        # Accept near-end seeks while the last buffered PCM drains.
                        draining = self.player and self.position_seconds() < self._sent_frames / SAMPLE_RATE - .04
                        if not seeking and not draining:
                            self._accept_seeks = False
                            break
                    self._stop.wait(.005)
                    continue
                if target:
                    remaining = memoryview(pcm)
                    while remaining:
                        written = target.write(remaining)
                        if not written:
                            raise BrokenPipeError("Audio output pipe closed.")
                        remaining = remaining[written:]
                    target.flush()
                self._sent_frames += len(pcm) // 4
                self._last_pcm_frame = pcm[-4:]
                try:
                    self.spectrum.feed(pcm)
                except Exception as exc:
                    self.spectrum.error = str(exc)
        except (BrokenPipeError, OSError, ValueError) as exc:
            if not self._stop.is_set() and (not self.player or self.player.poll() is None):
                self.error = str(exc)
        finally:
            with self._state_lock:
                self._accept_seeks = False
            self.decoder.stdout.close()
            if target:
                try:
                    target.close()
                except (BrokenPipeError, OSError):
                    pass

    def close(self, wait=True):
        self._stop.set()
        self._seek_wake.set()
        self.spectrum.close()
        with self._state_lock:
            self._accept_seeks = False
            stages = [self._stage, *self._retired]
            if self._preparing:
                stages.append(self._preparing)
            if self._ready:
                stages.append(self._ready[1])
        # First release blocked pipe reads/writes; their owning threads close them.
        for stage in stages:
            stage.close(wait=False)
        if self.player:
            if self._device_clock:
                self.player.terminate()
            else:
                _terminate(self.player, wait)
        if wait:
            for thread in self._threads:
                thread.join(timeout=1.5)
            for stage in stages:
                stage.close()
            self.spectrum.join()
