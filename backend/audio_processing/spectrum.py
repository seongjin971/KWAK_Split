"""Bounded analysis of the stereo PCM actually forwarded to the player.

No audio devices, Tk calls or extra rendering live here. The audio relay only
copies a window into a bounded queue; the worker does the FFT independently.
"""
from __future__ import annotations

from array import array
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
import math
import queue
import sys
import threading
import time

SAMPLE_RATE = 44100
FFT_SIZE = 8192
HOP_SIZE = 3072
FLOOR_DB = -90.0
FREQUENCIES = tuple(20 * 1000 ** (i / 159) for i in range(160))


@dataclass(frozen=True)
class SpectrumFrame:
    seconds: float
    levels: tuple[float, ...]


@lru_cache(maxsize=2)
def _fft_plan(size):
    bits = size.bit_length() - 1
    reverse = tuple(int(f"{i:0{bits}b}"[::-1], 2) for i in range(size))
    window = tuple(.5 - .5 * math.cos(2 * math.pi * i / size) for i in range(size))
    stages = []
    width = 2
    while width <= size:
        stages.append(tuple(complex(math.cos(-2 * math.pi * j / width),
                                    math.sin(-2 * math.pi * j / width))
                            for j in range(width // 2)))
        width *= 2
    return reverse, window, tuple(stages)


def analyze_pcm(pcm: bytes, sample_rate=SAMPLE_RATE) -> tuple[float, ...]:
    """Peak-bin amplitudes in dBFS, with coherent Hann gain and stereo RMS.

    Pack L+iR into one FFT. Combining the squared magnitudes of conjugate bins
    recovers channel power without averaging/cancelling antiphase audio.
    """
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    size = len(samples) // 2
    if size < 2 or size & (size - 1) or len(samples) != size * 2:
        raise ValueError("Spectrum requires a power-of-two stereo PCM window.")
    reverse, window, stages = _fft_plan(size)
    values = [complex(samples[2*i], samples[2*i+1]) * (window[i] / 32768)
              for i in reverse]
    width = 2
    for twiddles in stages:
        half = width // 2
        for start in range(0, size, width):
            for j, twiddle in enumerate(twiddles):
                a = start + j
                b = a + half
                odd = values[b] * twiddle
                even = values[a]
                values[a], values[b] = even + odd, even - odd
        width *= 2
    scale = sum(window)
    magnitudes = [math.sqrt(abs(values[k])**2 + abs(values[-k])**2) / scale
                  for k in range(size // 2 + 1)]
    # DC and Nyquist are not doubled; neither is inside the visible band.
    magnitudes[0] /= math.sqrt(2)
    magnitudes[-1] /= math.sqrt(2)
    step = sample_rate / size
    levels = []
    for i, frequency in enumerate(FREQUENCIES):
        left = frequency if i == 0 else math.sqrt(FREQUENCIES[i-1] * frequency)
        right = frequency if i == len(FREQUENCIES)-1 else math.sqrt(frequency * FREQUENCIES[i+1])
        first, last = max(1, math.ceil(left / step)), min(size // 2, math.floor(right / step))
        if first <= last:
            amplitude = max(magnitudes[first:last+1])
        else:
            position = min(size // 2 - 1, frequency / step)
            k = int(position)
            amplitude = magnitudes[k] + (magnitudes[k+1] - magnitudes[k]) * (position-k)
        levels.append(max(FLOOR_DB, min(0.0, 20 * math.log10(max(amplitude, 1e-12)))))
    return tuple(levels)


class SpectrumAnalyzer:
    def __init__(self):
        self._queue = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._frames = deque(maxlen=64)
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._samples = 0
        self._next = FFT_SIZE
        self.error = ""
        self.frames_analyzed = 0
        self.analysis_seconds = 0.0
        self._thread = threading.Thread(target=self._run, name="spectrum-fft", daemon=True)
        self._thread.start()

    def feed(self, pcm):
        if self._stop.is_set():
            return
        self._buffer.extend(pcm)
        self._samples += len(pcm) // 4
        if self._samples >= self._next and len(self._buffer) >= FFT_SIZE * 4:
            item = ((self._samples - FFT_SIZE / 2) / SAMPLE_RATE,
                    bytes(self._buffer[-FFT_SIZE*4:]))
            self._next = self._samples + HOP_SIZE
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    pass
        if len(self._buffer) > FFT_SIZE * 4:
            del self._buffer[:-FFT_SIZE*4]

    def frame_at(self, seconds):
        with self._lock:
            for frame in reversed(self._frames):
                if frame.seconds <= seconds:
                    return frame
        return None

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    item = self._queue.get(timeout=.1)
                except queue.Empty:
                    continue
                if item is None or self._stop.is_set():
                    break
                seconds, pcm = item
                started = time.monotonic()
                frame = SpectrumFrame(seconds, analyze_pcm(pcm))
                self.analysis_seconds += time.monotonic() - started
                self.frames_analyzed += 1
                with self._lock:
                    if not self._stop.is_set():
                        self._frames.append(frame)
        except Exception as exc:
            self.error = str(exc)

    def close(self):
        self._stop.set()
        # Wake an idle worker immediately instead of making transport wait for
        # the 100 ms queue timeout. A full queue already wakes the worker.
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        with self._lock:
            self._frames.clear()

    def join(self, timeout=.3):
        self._thread.join(timeout)
