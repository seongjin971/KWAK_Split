"""One idle preparation worker, one retained Windows device and one cached mix.

The worker never calls Tk. Immutable requests are captured by the UI; stale
preparations are closed without disturbing the current device session.
"""
from dataclasses import dataclass
import threading
import time

from backend.audio_processing.wave_output import create_output_device


@dataclass(frozen=True)
class PlaybackRequest:
    stems: tuple
    start_seconds: float
    duration_seconds: float
    fade_in: float
    fade_out: float
    effects: object
    fade_bounds: tuple

    def arguments(self):
        return dict(stems=self.stems, start_seconds=self.start_seconds,
                    duration_seconds=self.duration_seconds, fade_in=self.fade_in,
                    fade_out=self.fade_out, effects=self.effects, fade_bounds=self.fade_bounds)


class WarmTransport:
    def __init__(self, factory, device_factory=create_output_device):
        self._factory, self._device_factory = factory, device_factory
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._wake = threading.Event()
        self._closed = False
        self._serial = 0
        self._wanted = self._pending = self._cached = None
        self._retired = []
        self._building = self._retiring = False
        self._failure = None
        self.device = None
        self.unavailable = ""
        self.preparations = 0
        self._thread = threading.Thread(target=self._run, name="playback-prepare", daemon=True)
        self._thread.start()

    def prepare(self, request):
        with self._lock:
            if self._closed or self.unavailable or request == self._wanted:return
            self._serial += 1
            self._wanted = request
            self._pending = (self._serial, request)
            self._failure = None
            if self._cached:
                self._retired.append(self._cached[1]); self._cached = None
            self._wake.set()

    def take(self, request):
        with self._lock:
            if self._failure and self._failure[0] == request:raise self._failure[1]
            if not self._cached or self._cached[0] != request:return None
            owner = self._cached[1]
            if owner.error or owner.decoder.poll() not in (None, 0):
                raise OSError(owner.error or "The prepared audio decoder failed.")
            if owner.player.error:raise OSError(owner.player.error)
            # Prime several device packets before beginning audible playback.
            if owner.player.queued_seconds < .04 and not owner.player._eof:return None
            if owner._sent_frames == 0:raise OSError("The selected range produced no audio.")
            self._cached = self._wanted = self._pending = None
            self._serial += 1
            return owner

    def hold(self, owner, request):
        with self._lock:
            if self._closed:
                self._retired.append(owner)
            else:
                self._serial += 1
                self._wanted, self._pending = request, None
                self._failure = None
                if self._cached and self._cached[1] is not owner:
                    self._retired.append(self._cached[1])
                self._cached = (request, owner)
            self._wake.set()

    def cancel(self, wait=False):
        with self._lock:
            self._serial += 1
            self._wanted = self._pending = self._failure = None
            if self._cached:
                self._retired.append(self._cached[1]); self._cached = None
            self._wake.set()
            if wait:
                deadline = time.monotonic() + 4
                while self._building or self._retiring or self._retired:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:raise OSError("Audio preparation has not released the working files yet.")
                    self._condition.wait(remaining)

    def close(self, wait=True):
        self.cancel()
        with self._lock:self._closed = True
        self._wake.set()
        if wait:self._thread.join(timeout=4)

    def _run(self):
        try:
            # Opening some Windows drivers takes hundreds of ms. Do it outside
            # the request lock and UI thread, before the first file is loaded.
            try:self.device = self._device_factory()
            except OSError as exc:self.unavailable = str(exc)
            while True:
                self._wake.wait(.1); self._wake.clear()
                with self._lock:
                    retired, self._retired = self._retired, []
                    self._retiring = bool(retired)
                    work, self._pending = self._pending, None
                    closed = self._closed
                for owner in retired:owner.close()
                with self._condition:
                    self._retiring = False
                    self._condition.notify_all()
                if closed:return
                if not work or self.unavailable:continue
                serial, request = work
                owner = player = None
                try:
                    if self.device.failed:
                        self.device.close()
                        self.device = self._device_factory()
                    # A generation is reserved before process creation. Late
                    # work cannot reset a device subsequently handed to Play.
                    with self._lock:
                        if serial != self._serial or self._closed:continue
                        self._building = True
                        player = self.device.begin()
                    owner = self._factory(**request.arguments(), output_player=player)
                    self.preparations += 1
                    with self._lock:
                        if serial == self._serial and not self._closed:
                            self._cached = (request, owner); owner = player = None
                except Exception as exc:
                    with self._lock:
                        if serial == self._serial and not self._closed:
                            self._failure = (request, exc)
                finally:
                    if owner:owner.close()
                    elif player:player.terminate()
                    with self._condition:
                        self._building = False
                        self._condition.notify_all()
        finally:
            with self._lock:
                retired, self._retired = self._retired, []
                if self._cached:
                    retired.append(self._cached[1]); self._cached = None
            for owner in retired:owner.close()
            if self.device:self.device.close()
