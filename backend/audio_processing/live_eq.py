"""Latest-value EQ and mixer commands for an existing FFmpeg graph."""
from __future__ import annotations

import math
import socket
import threading
import time

try:
    import zmq
except ImportError:  # Unprepared source checkout: retain restart-based preview.
    zmq = None


class LiveEqController:
    """One worker owns its ZMQ socket; only a single desired state is retained."""

    RAMP_SECONDS = .04

    def __init__(self, parameters, dual_bank=False, mixer_weights=()):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.endpoint = f"tcp://127.0.0.1:{port}"
        self._current = dict(parameters)
        self._banks = [self._current, dict(parameters)]
        self._active_bank = 0
        self._dual_bank = dual_bank
        self._desired = dict(parameters)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self.error = ""
        self.revision = self.applied_revision = 0
        self._mixer_current = self._mixer_desired = tuple(mixer_weights)
        self.mixer_revision = self.mixer_applied_revision = 0
        self._mixer_ramp_revision = -1
        self._thread = threading.Thread(target=self._run, name="live-eq", daemon=True)

    @property
    def filter(self):
        address = self.endpoint.replace(":", "\\:")
        return f"azmq=b='{address}'"

    def start(self):
        self._thread.start()

    def submit(self, parameters):
        if self.error or self._stop.is_set() or parameters.keys() != self._current.keys():
            return False
        with self._lock:
            if parameters != self._desired:
                self._desired = dict(parameters)
                self.revision += 1
        self._wake.set()
        return True

    def close(self):
        self._stop.set()
        self._wake.set()

    def submit_mixer(self, weights):
        weights = tuple(weights)
        if (self.error or self._stop.is_set() or not self._mixer_current
                or len(weights) != len(self._mixer_current)
                or any(not math.isfinite(v) or v < 0 for v in weights)):
            return False
        weights = tuple(round(v, 6) for v in weights)
        with self._lock:
            if weights != self._mixer_desired:
                self._mixer_desired = weights
                self.mixer_revision += 1
        self._wake.set()
        return True

    def _step_mixer(self, channel):
        with self._lock:
            desired, revision = self._mixer_desired, self.mixer_revision
        if revision != self._mixer_ramp_revision:
            self._mixer_origin = self._mixer_current
            self._mixer_started = time.monotonic()
            self._mixer_ramp_revision = revision
        if desired != self._mixer_current:
            amount = min(1, (time.monotonic() - self._mixer_started + .004) / self.RAMP_SECONDS)
            weights = tuple(round(a + amount * (b - a), 6)
                            for a, b in zip(self._mixer_origin, desired))
            if weights != self._mixer_current:
                # One command changes all four tracks together, including Solo.
                argument = "'" + " ".join(f"{v:.6f}" for v in weights) + "'"
                if not self._command(channel, "amix@kw_stems", "weights", argument):
                    return False
                self._mixer_current = weights
        if desired == self._mixer_current:
            self.mixer_applied_revision = revision
        return True

    def join(self):
        if self._thread.ident is not None:
            self._thread.join(timeout=.3)

    def _poll(self, channel, event):
        deadline = time.monotonic() + 2
        while not self._stop.is_set():
            if channel.poll(20, event):
                return True
            if time.monotonic() >= deadline:
                raise TimeoutError("The audio engine did not acknowledge the live change.")
        return False

    def _command(self, channel, target, parameter, value):
        if not self._poll(channel, zmq.POLLOUT):
            return False
        argument = value if isinstance(value, str) else f"{value:.3f}"
        channel.send_string(f"{target} {parameter} {argument}")
        if not self._poll(channel, zmq.POLLIN):
            return False
        reply = channel.recv_string()
        if reply.split(maxsplit=1)[0] != "0":
            raise RuntimeError(f"Audio command rejected: {reply[:180]}")
        return True

    def _target(self, target, bank=None):
        if not self._dual_bank:
            return target
        return bank_target(target, self._active_bank if bank is None else bank)

    def _switch_bank(self, channel, desired):
        """Configure the inaudible branch, then change both gains atomically."""
        destination = 1 - self._active_bank
        prepared = self._banks[destination]
        for (target, parameter), value in desired.items():
            if not self._step_mixer(channel):
                return False
            if prepared[target, parameter] != value:
                if not self._command(channel, self._target(target, destination), parameter, value):
                    return False
                prepared[target, parameter] = value
        # Both branches continuously process PCM, including when their weight is
        # zero. Allow the reconfigured filter state to settle before fading in.
        if self._stop.wait(.03):
            return False
        started = time.monotonic()
        amount = 0.0
        while not self._stop.is_set():
            if not self._step_mixer(channel):
                return False
            # A delayed command or scheduler wake must not skip most of the
            # crossfade in one step. Keep fading smoothly even when it takes
            # longer than the nominal duration under load.
            amount = min(1, round(amount + .1, 6),
                         (time.monotonic() - started + .004) / self.RAMP_SECONDS)
            weights = (1-amount, amount) if destination == 1 else (amount, 1-amount)
            # azmq tokenizes ARG on whitespace; quote the pair as one argument.
            if not self._command(channel, "amix@kw_eq_crossfade", "weights",
                                 f"'{weights[0]:.6f} {weights[1]:.6f}'"):
                return False
            if amount == 1:
                self._active_bank = destination
                self._current = prepared
                return True
            if self._stop.wait(.004):
                return False
        return False

    def _run(self):
        context = channel = None
        revision = -1
        try:
            context = zmq.Context()
            channel = context.socket(zmq.REQ)
            channel.setsockopt(zmq.LINGER, 0)
            channel.setsockopt(zmq.IMMEDIATE, 1)
            channel.connect(self.endpoint)
            while not self._stop.is_set():
                self._wake.wait(.05)
                self._wake.clear()
                while not self._stop.is_set():
                    if not self._step_mixer(channel):
                        return
                    with self._lock:
                        desired, latest = dict(self._desired), self.revision
                    if latest != revision:
                        origin = dict(self._current)
                        started = time.monotonic()
                        revision = latest
                    if desired == self._current:
                        self.applied_revision = revision
                        if self.mixer_applied_revision == self.mixer_revision:
                            break
                        if self._stop.wait(.004):
                            return
                        continue
                    if self._dual_bank and any(value != self._current[key]
                                               for key, value in desired.items() if key[1] == "m"):
                        if not self._switch_bank(channel, desired):
                            return
                        continue
                    # Small, bounded ramps; frequency and Q move logarithmically.
                    amount = min(1, (time.monotonic() - started + .004) / self.RAMP_SECONDS)
                    for (target, parameter), value in desired.items():
                        before = origin[target, parameter]
                        if parameter in ("f", "w"):
                            step = math.exp(math.log(before) + amount * math.log(value / before))
                        else:
                            step = before + amount * (value - before)
                        step = round(value if amount == 1 else step, 3)
                        if step != self._current[target, parameter]:
                            if not self._command(channel, self._target(target), parameter, step):
                                return
                            self._current[target, parameter] = step
                    if self._stop.wait(.004):
                        return
        except Exception as exc:
            if not self._stop.is_set():
                self.error = str(exc)
        finally:
            if channel is not None:
                channel.close()
            if context is not None:
                context.term()


def available():
    return zmq is not None


def bank_target(target, bank):
    return target + ("_a" if bank == 0 else "_b")
