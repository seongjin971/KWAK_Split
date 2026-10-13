"""In-memory audio adjustments and per-file Undo/Redo."""
import copy
import math

from backend.compact_model import MAX_STEM_PERCENT

EDIT_DEFAULTS = {
    "selection_start": 0.0, "selection_end": 0.0,
    "fade_in": 0.02, "fade_out": 0.02,
    "eq_low": 0.0, "eq_mid": 0.0, "eq_high": 0.0,
    "eq_low_freq": 120.0, "eq_mid_freq": 1000.0, "eq_high_freq": 8000.0,
    "eq_low_q": 0.8, "eq_mid_q": 1.0, "eq_high_q": 0.8,
    "eq_low_shape": "Low Shelf", "eq_mid_shape": "Bell", "eq_high_shape": "High Shelf",
    "high_pass": 0.0, "low_pass": 0.0, "high_pass_q": 0.7, "low_pass_q": 0.7,
    "high_pass_slope": 24, "low_pass_slope": 24,
    "pitch_semitones": 0.0, "tempo_percent": 100.0,
    "peak_normalize": False, "limiter_enabled": True, "limiter_ceiling": 0.98,
    "stem_bypass": False, "loop": True, "sample_rate": 48000, "bit_depth": 24,
    "mp3_bitrate": 320,
}


def validate_edits(edits):
    if not isinstance(edits, dict):
        raise ValueError("Invalid audio settings format.")
    result = dict(EDIT_DEFAULTS)
    for name, default in EDIT_DEFAULTS.items():
        value = edits.get(name, default)
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f"Invalid setting: {name}")
        elif isinstance(default, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid number: {name}")
        elif value not in ("Bell", "Low Shelf", "High Shelf", "High Pass", "Low Pass"):
            raise ValueError(f"Invalid EQ shape: {name}")
        result[name] = value
    for key in ("high_pass_slope", "low_pass_slope"):
        if result[key] not in (12, 24, 36, 48):
            raise ValueError("Filter slope must be 12, 24, 36 or 48 dB/oct.")
    for key in ("fade_in", "fade_out"):
        if not 0 <= result[key] <= 10:
            raise ValueError("Fade duration must be between 0 and 10 seconds.")
    if result["sample_rate"] not in (44100, 48000) or result["bit_depth"] not in (16, 24):
        raise ValueError("Unsupported WAV format.")
    if result["mp3_bitrate"] not in (128, 192, 256, 320):
        raise ValueError("Unsupported MP3 bitrate.")
    if not 50 <= result["tempo_percent"] <= 200 or not -12 <= result["pitch_semitones"] <= 12:
        raise ValueError("Pitch or speed is outside the supported range.")
    stems = edits.get("stems", {})
    if not isinstance(stems, dict):
        raise ValueError("Invalid stem settings.")
    result["stems"] = {}
    for stem in ("vocals", "drums", "bass", "other"):
        values = stems.get(stem, {"volume": 100.0, "mute": False, "solo": False})
        if not isinstance(values, dict):
            raise ValueError("Invalid stem settings.")
        volume = values.get("volume", 100.0)
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= MAX_STEM_PERCENT + 1e-6:
            raise ValueError("Stem volume must be between silence and +12 dB.")
        if not all(isinstance(values.get(key, False), bool) for key in ("mute", "solo")):
            raise ValueError("Invalid Mute/Solo value.")
        result["stems"][stem] = {"volume": volume, "mute": values.get("mute", False), "solo": values.get("solo", False)}
    return result


class EditHistory:
    def __init__(self, state, limit=100):
        self.states = [copy.deepcopy(state)]
        self.index = 0
        self.limit = limit

    def push(self, state):
        if state == self.states[self.index]:
            return
        self.states = self.states[:self.index + 1] + [copy.deepcopy(state)]
        self.states = self.states[-self.limit:]
        self.index = len(self.states) - 1

    def undo(self):
        self.index = max(0, self.index - 1)
        return copy.deepcopy(self.states[self.index])

    def redo(self):
        self.index = min(len(self.states) - 1, self.index + 1)
        return copy.deepcopy(self.states[self.index])
